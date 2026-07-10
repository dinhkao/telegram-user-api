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


def compute_stock_demand() -> dict:
    conn = _get_connection()
    try:
        return _compute(conn)
    finally:
        conn.close()


def _compute(conn) -> dict:
    from product_store import resolve_code
    threshold = _today_vn_utc_iso()
    # đơn ứng viên: tạo từ hôm nay, chưa chốt xuất kho (đơn đã chốt = đã phân bổ đủ)
    rows = conn.execute(
        "SELECT thread_id, json FROM orders "
        "WHERE json_extract(json,'$.created') >= ? "
        "AND json_extract(json,'$.stock_confirmed') IS NULL",
        (threshold,),
    ).fetchall()

    codemap: dict = {}                 # mã → product dict (cache resolve)
    demand: dict = {}                  # key → {code,name,pid,orders:set}
    per_order: dict = {}               # (tid, key) → Σ sl gross
    for r in rows:
        try:
            j = json.loads(r["json"] or "{}")
        except Exception:
            continue
        if not isinstance(j, dict) or _delivered(j):
            continue                   # đã giao → hàng đã ra, không tính
        tid = r["thread_id"]
        for it in (j.get("invoice") or j.get("invoice_items") or []):
            code = str(it.get("sp") or "").strip().upper()
            if not code:
                continue
            sl = _num(it.get("sl") or it.get("quantity") or it.get("sl1pc") or 0)
            if sl <= 0:
                continue
            if code not in codemap:
                codemap[code] = resolve_code(conn, code)
            prod = codemap[code]
            key = prod["id"] if prod else f"c:{code}"
            per_order[(tid, key)] = per_order.get((tid, key), 0.0) + sl
            d = demand.setdefault(key, {"code": (prod["code"] if prod else code),
                                        "pid": (prod["id"] if prod else None), "orders": set()})
            d["orders"].add(tid)

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

    # nhu cầu ròng theo SP = Σ max(0, gross − đã xuất) từng đơn
    net: dict = {}
    for (tid, key), gross in per_order.items():
        got = alloc.get((tid, key), 0.0) if isinstance(key, int) else 0.0
        net[key] = net.get(key, 0.0) + max(0.0, gross - got)

    # tồn theo product_id (thùng còn hiệu lực)
    stock: dict = {}
    for s in conn.execute(
        "SELECT b.product_id AS pid, "
        "SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS rem "
        "FROM inventory_boxes b WHERE (b.disabled IS NULL OR b.disabled = 0) GROUP BY b.product_id",
    ).fetchall():
        stock[s["pid"]] = float(s["rem"] or 0)

    # tên/đơn vị hiện hành
    names = {r["id"]: (r["name"], r["unit"]) for r in conn.execute(
        "SELECT id, name, unit FROM products").fetchall()}

    products = []
    for key, need in net.items():
        if need <= 1e-9:
            continue
        d = demand[key]
        pid = d["pid"]
        st = stock.get(pid, 0.0) if pid is not None else 0.0
        nm, unit = names.get(pid, ("", "")) if pid is not None else ("", "")
        short = max(0.0, need - st)
        products.append({
            "code": d["code"], "name": nm or "", "unit": unit or "",
            "need": round(need, 3), "stock": round(st, 3),
            "enough": st + 1e-9 >= need, "shortfall": round(short, 3),
            "orders": len(d["orders"]),
        })
    products.sort(key=lambda p: (-p["shortfall"], -p["need"], p["code"]))

    short_products = [p for p in products if not p["enough"]]
    order_ids = {tid for (tid, key), g in per_order.items()
                 if max(0.0, g - (alloc.get((tid, key), 0.0) if isinstance(key, int) else 0.0)) > 1e-9}
    return {
        "ok": True, "since": threshold, "products": products,
        "totals": {
            "orders": len(order_ids),
            "product_lines": len(products),
            "short_products": len(short_products),
            "total_need": round(sum(p["need"] for p in products), 3),
            "total_shortfall": round(sum(p["shortfall"] for p in products), 3),
            "all_enough": len(short_products) == 0,
        },
    }


async def stock_demand_handler(request: web.Request):
    data = await asyncio.to_thread(compute_stock_demand)
    return web.json_response(data)
