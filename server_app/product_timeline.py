"""Timeline biến động TỒN của 1 SẢN PHẨM — GET /api/inventory/{code}/timeline.

Gộp biến động qua MỌI THÙNG của SP (audit_events scope='box', ghi bởi inventory_audit):
sản xuất nhập kho / xuất cho đơn / thu về / tiêu hao đóng gói SP khác. Tính DELTA
(+vào / −ra) + TỒN TỔNG CHẠY (total_after) bằng cách lấy tồn HIỆN TẠI của SP rồi đi
ngược thời gian — giống place_timeline nhưng gom theo product_id (bất biến, chịu được
đổi mã). Trả current_boxes (dựng lại "SP nằm ở thùng nào" khi bấm chấm) + current_by_place.
Nối: product_store.resolve, inventory_boxes, box_allocations, order_history (tên actor).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web

from order_db import _get_connection
from server_app.order_history import _actor_display, _load_names

_CAP = 500
# CHỈ các biến động ĐỔI TỒN của SP (bỏ chuyển kho/chuyển thùng — nội bộ, tồn SP không đổi)
_ACTIONS = ("box.created", "box.allocated", "box.released", "box.consumed", "box.disposed", "box.disposal_released",
            "box.purchase_in", "box.purchase_in_removed", "box.return_in",
            "adjustment.created", "adjustment.deleted")
_DIR_IN = {"box.created", "box.released", "box.disposal_released", "box.purchase_in", "box.return_in"}
# Điều chỉnh tồn: chiều +/− theo DẤU delta (không cố định như action khác)
_SIGNED = {"adjustment.created", "adjustment.deleted"}
_REASON = {"box.created": "sản xuất nhập kho", "box.allocated": "xuất cho đơn",
           "box.released": "thu về từ đơn", "box.consumed": "tiêu hao đóng gói",
           "box.disposed": "xuất hủy", "box.disposal_released": "hoàn xuất hủy",
           "box.purchase_in": "nhập hàng NCC", "box.purchase_in_removed": "gỡ nhập hàng NCC",
           "box.return_in": "khách trả về",
           "adjustment.created": "điều chỉnh tồn", "adjustment.deleted": "gỡ điều chỉnh tồn"}


def _created_reason(p: dict) -> str:
    """box.created có nguồn khác phiếu SX → nhãn theo payload (phiếu nhập / hàng trả)."""
    if p.get("purchase_id"):
        return "nhập hàng NCC (thùng mới)"
    if p.get("return_id"):
        return "khách trả về (thùng mới)"
    return _REASON["box.created"]


def _delta(action: str, p: dict) -> float:
    """Ảnh hưởng lên TỒN của SP — + (vào) / − (ra)."""
    q = float(p.get("quantity") or 0)
    rem = p.get("remaining")
    rem = float(rem) if rem is not None else q
    taken = float(p.get("taken") or 0)
    try:
        adj = float(p.get("delta") or 0)
    except (TypeError, ValueError):
        adj = 0.0
    return {"box.created": rem, "box.released": taken,
            "box.allocated": -taken, "box.consumed": -taken,
            "box.disposed": -taken, "box.disposal_released": taken,
            "box.purchase_in": taken, "box.purchase_in_removed": -taken,
            "box.return_in": taken,
            "adjustment.created": adj, "adjustment.deleted": -adj}.get(action, 0.0)


def _epoch(ts: str) -> int:
    try:
        return int(datetime.fromisoformat((ts or "").replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def _boxnum(code) -> str:
    s = str(code or "")
    return s.split("-")[-1] or s


def _product_stock(conn, pid: int) -> tuple[float, int]:
    """Tồn hiện tại của SP (Σ remaining thùng còn hiệu lực) + số thùng còn hàng."""
    row = conn.execute(
        "SELECT COALESCE(SUM(rem),0) AS total, SUM(CASE WHEN rem > 0.0001 THEN 1 ELSE 0 END) AS c FROM ("
        "  SELECT b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS rem "
        "  FROM inventory_boxes b WHERE b.product_id = ? AND (b.disabled IS NULL OR b.disabled = 0)"
        ")",
        (pid,),
    ).fetchone()
    return float(row[0] or 0), int(row[1] or 0)


def _by_place(conn, pid: int) -> list[dict]:
    """SP hiện đang nằm ở những kho nào (tồn theo vị trí, giảm dần)."""
    rows = conn.execute(
        "SELECT COALESCE(pl.name,'(chưa xếp)') AS place, "
        "SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS qty "
        "FROM inventory_boxes b LEFT JOIN inventory_places pl ON pl.id = b.place_id "
        "WHERE b.product_id = ? AND (b.disabled IS NULL OR b.disabled = 0) "
        "GROUP BY place HAVING qty > 0.0001 ORDER BY qty DESC",
        (pid,),
    ).fetchall()
    return [{"place": r[0], "qty": round(float(r[1] or 0), 3)} for r in rows]


def _current_boxes(conn, pid: int) -> list[dict]:
    """Thùng HIỆN CÓ của SP (đủ field cho BoxLabelGrid + dựng lại lịch sử box set)."""
    rows = conn.execute(
        "SELECT b.id, b.box_code, COALESCE(pr.code, b.product_code) AS product_code, b.quantity, "
        "b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS remaining, "
        "COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS allocated, "
        "b.quantity + COALESCE((SELECT SUM(CASE WHEN x.quantity < 0 THEN -x.quantity ELSE 0 END) FROM box_allocations x WHERE x.box_id=b.id),0) AS capacity, "
        "COALESCE(pr.unit,'cây') AS product_unit, b.note, pl.name AS place_name "
        "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
        "LEFT JOIN inventory_places pl ON pl.id = b.place_id "
        "WHERE b.product_id = ? AND (b.disabled IS NULL OR b.disabled = 0)",
        (pid,),
    ).fetchall()
    return [{"id": r["id"], "box_code": r["box_code"], "product_code": r["product_code"],
             "quantity": float(r["quantity"] or 0), "remaining": float(r["remaining"] or 0),
             "allocated": float(r["allocated"] or 0), "capacity": float(r["capacity"] or 0),
             "product_unit": r["product_unit"],
             "place_name": r["place_name"], "note": r["note"], "disabled": False} for r in rows]


def product_timeline(code: str) -> dict:
    from product_store import resolve_code
    conn = _get_connection()
    try:
        prod = resolve_code(conn, code)
        if not prod:
            return {"ok": False, "error": "Không tìm thấy sản phẩm"}
        pid = prod["id"]
        unit = prod.get("unit") or "cây"
        box_ids = [r[0] for r in conn.execute(
            "SELECT id FROM inventory_boxes WHERE product_id = ?", (pid,)).fetchall()]
        current, box_count = _product_stock(conn, pid)
        rows = []
        if box_ids:
            am = ",".join("?" * len(_ACTIONS))
            qm = ",".join("?" * len(box_ids))
            rows = conn.execute(
                "SELECT ts, actor_id, action, payload_json FROM audit_events "
                f"WHERE scope = 'box' AND action IN ({am}) AND thread_id IN ({qm}) "
                "ORDER BY id DESC LIMIT ?",
                (*_ACTIONS, *box_ids, _CAP),
            ).fetchall()
        names = _load_names()
        items = []
        running = current
        for r in rows:
            act = r["action"]
            try:
                p = json.loads(r["payload_json"] or "{}")
                p = p if isinstance(p, dict) else {}
            except Exception:
                p = {}
            delta = _delta(act, p)
            items.append({
                "ts": _epoch(r["ts"]), "at": r["ts"],
                "dir": ("in" if delta >= 0 else "out") if act in _SIGNED else ("in" if act in _DIR_IN else "out"),
                "kind": act.replace("box.", ""),
                "reason": _created_reason(p) if act == "box.created" else _REASON.get(act, ""),
                "product_code": p.get("product_code") or prod["code"],
                "box_id": p.get("box_id"), "box_code": p.get("box_code"), "box_num": _boxnum(p.get("box_code")),
                "quantity": p.get("quantity"), "delta": round(delta, 3), "amount": round(abs(delta), 3),
                "remaining": p.get("remaining"),   # tồn của THÙNG sau biến động
                "order_thread_id": p.get("order_thread_id"), "order_text": p.get("order_text"),
                "target_code": p.get("target_code"), "slip_id": p.get("slip_id"),   # tiêu hao đóng gói
                "disposal_id": p.get("disposal_id"), "disposal_reason": p.get("disposal_reason"),
                "purchase_id": p.get("purchase_id"), "return_id": p.get("return_id"),   # nhập hàng / hàng trả
                "adjustment_id": p.get("adjustment_id"), "adjust_reason": p.get("reason"),   # phiếu điều chỉnh
                "total_after": round(running, 3), "unit": unit,
                "actor": _actor_display(r["actor_id"], names),
            })
            running -= delta
        return {"ok": True,
                "product": {"id": pid, "code": prod["code"], "name": prod.get("name") or "",
                            "unit": unit, "min_stock": float(prod.get("min_stock") or 0)},
                "current_total": round(current, 3), "box_count": box_count,
                "current_by_place": _by_place(conn, pid),
                "current_boxes": _current_boxes(conn, pid),
                "items": items, "truncated": len(rows) >= _CAP}
    finally:
        conn.close()


async def product_timeline_handler(request: web.Request):
    code = request.match_info.get("code", "")
    if not code:
        return web.json_response({"ok": False, "error": "thiếu mã SP"}, status=400)
    data = await asyncio.to_thread(product_timeline, code)
    return web.json_response(data, status=200 if data.get("ok") else 404)
