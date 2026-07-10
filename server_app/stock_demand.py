"""Nhu cầu kho vs tồn — GET /api/inventory/demand.

Tổng hàng mà các ĐƠN CHƯA PHÂN BỔ (tạo TỪ HÔM NAY trở đi — tính năng kho mới nên
chỉ tính đơn mới; chưa chốt xuất kho; chưa giao) còn CẦN, đối chiếu tồn kho hiện tại
theo từng SP → đủ / thiếu bao nhiêu.

Nhu cầu chưa phân bổ = Σ(invoice sl) − Σ(đã xuất kho cho đơn đó), cộng theo SP
(danh tính = product_id, resolve mã cũ). Tồn = Σ remaining thùng còn hiệu lực.
Đọc: orders blob ($.invoice), box_allocations (kind='order'), inventory_boxes,
products. Không ghi gì. Nối: product_store.resolve, utils qua order_db.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from aiohttp import web

from order_db import _get_connection

_VN = timezone(timedelta(hours=7))
# Mốc bắt đầu tính nhu cầu: đơn tạo TỪ 07/07/2026 (giờ VN) trở đi — flow kho bắt đầu
# từ đây; đơn cũ hơn chưa qua flow kho nên bỏ. (00:00 VN 07/07 = 17:00 UTC 06/07)
_SINCE_ISO = "2026-07-06T17:00:00.000Z"


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _today_vn_utc_iso() -> str:
    """00:00 hôm nay theo giờ VN, quy về ISO UTC (khớp $.created dạng ...Z)."""
    now = datetime.now(_VN)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _delivered(j: dict) -> bool:
    if j.get("giao") in (True, 1, "true"):
        return True
    ts = j.get("task_status") or {}
    return bool((ts.get("giao_hang") or {}).get("done"))


def _ingredients(conn, code, produced_qty, stock, names, depth=0, seen=None) -> list:
    """Cây gợi ý NGUYÊN LIỆU (BOM) để LÀM `produced_qty` cây `code`.
    NL cần = ratio × produced_qty (0 nếu chỉ để tham khảo tồn). NL nào CÒN THIẾU
    (need > tồn) + có công thức riêng → đệ quy gợi ý NL cấp dưới (children). Chặn
    vòng lặp bằng `seen`, giới hạn 5 tầng. Trả [] nếu SP không có công thức."""
    from recipe_store import list_recipe
    seen = seen or set()
    key = str(code or "").upper()
    if depth > 5 or key in seen:
        return []
    seen = seen | {key}
    out = []
    for rl in list_recipe(conn, code):
        iid = rl.get("ingredient_id")
        m_need = round(float(rl.get("ratio") or 0) * float(produced_qty or 0), 3)
        m_stock = round(float(stock.get(iid, 0.0)), 3) if iid is not None else 0.0
        inm, iunit = names.get(iid, ("", "")) if iid is not None else ("", "")
        m_short = round(max(0.0, m_need - m_stock), 3)
        # NL cũng thiếu → phải LÀM m_short cái NL này → gợi ý NL cấp dưới
        children = _ingredients(conn, rl.get("ingredient_code"), m_short, stock, names, depth + 1, seen) if m_short > 1e-9 else []
        out.append({
            "code": rl.get("ingredient_code"), "name": inm or "", "unit": iunit or "",
            "need": m_need, "stock": m_stock,
            "enough": m_stock + 1e-9 >= m_need, "shortfall": m_short, "children": children,
        })
    return out


def _order_label(j: dict, tid) -> str:
    # Nhãn đơn = TEXT đơn (gộp xuống dòng thành khoảng trắng, cắt gọn), fallback #id
    txt = (j.get("text") or j.get("text_raw") or "").strip()
    return " ".join(txt.split())[:60] if txt else f"#{tid}"


def compute_stock_demand() -> dict:
    conn = _get_connection()
    try:
        return _compute(conn)
    finally:
        conn.close()


def _compute(conn) -> dict:
    from product_store import resolve_code
    threshold = _SINCE_ISO
    # đơn ứng viên: tạo TỪ 07/07/2026, chưa chốt xuất kho (đơn đã chốt = đã phân bổ đủ)
    rows = conn.execute(
        "SELECT thread_id, json FROM orders "
        "WHERE json_extract(json,'$.created') >= ? "
        "AND json_extract(json,'$.stock_confirmed') IS NULL "
        "AND deleted_at IS NULL",   # bỏ đơn đã xoá mềm (bấm vào sẽ 404)
        (threshold,),
    ).fetchall()

    codemap: dict = {}                 # mã → product dict (cache resolve)
    demand: dict = {}                  # key → {code,name,pid,orders:set}
    per_order: dict = {}               # (tid, key) → Σ sl gross
    order_label: dict = {}             # tid → nhãn đơn (khách / dòng đầu text)
    order_ngay: dict = {}              # tid → ngày giao (ISO) để xếp gấp
    empty_orders: list = []            # đơn (đã qua lọc) CHƯA nhập SP nào → cảnh báo
    for r in rows:
        try:
            j = json.loads(r["json"] or "{}")
        except Exception:
            continue
        if not isinstance(j, dict) or _delivered(j):
            continue                   # đã giao → hàng đã ra, không tính
        tid = r["thread_id"]
        order_label[tid] = _order_label(j, tid)
        order_ngay[tid] = str(j.get("ngay_giao") or "")
        had_item = False
        for it in (j.get("invoice") or j.get("invoice_items") or []):
            code = str(it.get("sp") or "").strip().upper()
            if not code:
                continue
            sl = _num(it.get("sl") or it.get("quantity") or it.get("sl1pc") or 0)
            if sl <= 0:
                continue
            had_item = True
            if code not in codemap:
                codemap[code] = resolve_code(conn, code)
            prod = codemap[code]
            key = prod["id"] if prod else f"c:{code}"
            per_order[(tid, key)] = per_order.get((tid, key), 0.0) + sl
            d = demand.setdefault(key, {"code": (prod["code"] if prod else code),
                                        "pid": (prod["id"] if prod else None), "orders": set()})
            d["orders"].add(tid)
        if not had_item:               # đơn chưa nhập SP nào → nhu cầu có thể thiếu
            empty_orders.append({"thread_id": tid, "label": order_label[tid]})

    tids = [r["thread_id"] for r in rows]
    # đã xuất kho cho các đơn này, theo (đơn, product_id)
    alloc: dict = {}
    if tids:
        qm = ",".join("?" * len(tids))
        for a in conn.execute(
            f"SELECT a.order_thread_id AS tid, b.product_id AS pid, COALESCE(SUM(a.quantity),0) AS q "
            f"FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id "
            f"WHERE a.kind = 'order' AND a.order_thread_id IN ({qm}) "
            f"GROUP BY a.order_thread_id, b.product_id", tids,
        ).fetchall():
            alloc[(a["tid"], a["pid"])] = float(a["q"] or 0)

    # nhu cầu ròng theo SP = Σ max(0, gross − đã xuất) từng đơn; kèm breakdown theo đơn
    net: dict = {}
    porders: dict = {}                 # key → [{thread_id, need, label}] (đơn còn cần SP này)
    for (tid, key), gross in per_order.items():
        got = alloc.get((tid, key), 0.0) if isinstance(key, int) else 0.0
        un = max(0.0, gross - got)
        net[key] = net.get(key, 0.0) + un
        if un > 1e-9:
            porders.setdefault(key, []).append(
                {"thread_id": tid, "need": round(un, 3), "label": order_label.get(tid, f"#{tid}"),
                 "ngay_giao": order_ngay.get(tid, "")})
    for lst in porders.values():
        lst.sort(key=lambda o: -o["need"])

    # tồn theo product_id (thùng còn hiệu lực)
    stock: dict = {}
    for s in conn.execute(
        "SELECT b.product_id AS pid, "
        "SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS rem "
        "FROM inventory_boxes b WHERE (b.disabled IS NULL OR b.disabled = 0) GROUP BY b.product_id",
    ).fetchall():
        stock[s["pid"]] = float(s["rem"] or 0)

    # tên/đơn vị + có SX trực tiếp được không, theo product_id hiện hành
    names, candirect = {}, {}
    for r in conn.execute("SELECT id, name, unit, can_produce_directly FROM products").fetchall():
        names[r["id"]] = (r["name"], r["unit"])
        candirect[r["id"]] = (r["can_produce_directly"] != 0)

    products = []
    for key, need in net.items():
        if need <= 1e-9:
            continue
        d = demand[key]
        pid = d["pid"]
        st = stock.get(pid, 0.0) if pid is not None else 0.0
        nm, unit = names.get(pid, ("", "")) if pid is not None else ("", "")
        short = max(0.0, need - st)
        # Gợi ý NGUYÊN LIỆU: LUÔN hiện nếu SP có công thức (kể cả SP đủ hàng — tồn NL
        # ảnh hưởng quyết định). NL cần = ratio × phần thiếu (0 khi đủ → chỉ xem tồn).
        # Đệ quy: NL cũng thiếu → gợi ý NL cấp dưới.
        ingredients = _ingredients(conn, d["code"], short, stock, names)
        # Số cây 1 mâm → quy phần thiếu ra "≈ N mâm" (tiếng nghề, thợ hiểu ngay)
        cpm = 0.0
        if short > 1e-9:
            try:
                from production_store.defaults import production_defaults
                cpm = float(production_defaults(conn, d["code"])[0] or 0)
            except Exception:
                cpm = 0.0
        products.append({
            "code": d["code"], "name": nm or "", "unit": unit or "",
            "need": round(need, 3), "stock": round(st, 3),
            "enough": st + 1e-9 >= need, "shortfall": round(short, 3),
            "orders": len(d["orders"]), "orders_detail": porders.get(key, []),
            "ingredients": ingredients, "cay_per_mam": round(cpm, 3),
            "can_direct": candirect.get(pid, True) if pid is not None else True,
        })
    products.sort(key=lambda p: (-p["shortfall"], -p["need"], p["code"]))

    short_products = [p for p in products if not p["enough"]]
    order_ids = {tid for (tid, key), g in per_order.items()
                 if max(0.0, g - (alloc.get((tid, key), 0.0) if isinstance(key, int) else 0.0)) > 1e-9}
    return {
        "ok": True, "since": threshold, "products": products,
        "no_products": empty_orders,   # đơn qua lọc nhưng chưa nhập SP → cảnh báo
        "totals": {
            "orders": len(order_ids),
            "product_lines": len(products),
            "short_products": len(short_products),
            "total_need": round(sum(p["need"] for p in products), 3),
            "total_shortfall": round(sum(p["shortfall"] for p in products), 3),
            "all_enough": len(short_products) == 0,
            "orders_no_products": len(empty_orders),
        },
    }


async def stock_demand_handler(request: web.Request):
    data = await asyncio.to_thread(compute_stock_demand)
    return web.json_response(data)
