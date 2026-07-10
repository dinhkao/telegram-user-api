"""Timeline biến động của 1 VỊ TRÍ KHO — GET /api/places/{id}/timeline.

Rút gọn còn 2 loại: THÙNG VÀO / THÙNG RA. Đọc audit_events scope='place' (ghi bởi
server_app/inventory_audit), tính DELTA (+vào / −ra) + TỒN CHẠY (total_after) bằng
cách lấy tồn HIỆN TẠI rồi đi ngược thời gian. Trả thêm current_by_product (tồn theo
SP hiện tại) → client dựng lại "kho chứa gì" tại mỗi mốc khi bấm chấm tròn. Mỗi item
kèm box_id để card link tới lịch sử thao tác của thùng đó. Best-effort với bản ghi cũ.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web

from order_db import _get_connection
from server_app.order_history import _actor_display, _load_names

_CAP = 500

_DIR_IN = {"box.created", "box.moved_in", "box.released", "box.transfer_in"}
_DIR_OUT = {"box.allocated", "box.moved_out", "box.deleted", "box.transfer_out"}
_INV_ACTIONS = _DIR_IN | _DIR_OUT
_REASON = {
    "box.created": "nhập kho", "box.moved_in": "chuyển đến", "box.released": "trả về đơn",
    "box.transfer_in": "nhận chuyển", "box.allocated": "xuất cho đơn", "box.moved_out": "chuyển đi",
    "box.deleted": "xoá thùng", "box.transfer_out": "chuyển sang thùng khác",
}


def _delta(action: str, p: dict) -> float:
    """Ảnh hưởng lên TỒN (Σ remaining) của kho — + (vào) / − (ra)."""
    q = float(p.get("quantity") or 0)
    rem = p.get("remaining")
    rem = float(rem) if rem is not None else q
    taken = float(p.get("taken") or 0)
    return {
        "box.created": rem, "box.moved_in": rem, "box.released": taken, "box.transfer_in": q,
        "box.allocated": -taken, "box.moved_out": -rem, "box.deleted": -q, "box.transfer_out": -q,
    }.get(action, 0.0)


def _epoch(ts: str) -> int:
    try:
        return int(datetime.fromisoformat((ts or "").replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def _boxnum(code) -> str:
    s = str(code or "")
    return s.split("-")[-1] or s


def _place_stock(conn, place_id: int) -> tuple[float, int]:
    # box_count = CHỈ thùng CÒN HÀNG (thùng đã xuất hết / chuyển hết = rỗng, ẩn khỏi kho
    # nên không đếm — khớp danh sách hiển thị, khỏi phình số "thùng ma").
    row = conn.execute(
        "SELECT COALESCE(SUM(rem),0) AS total, "
        "SUM(CASE WHEN rem > 0.0001 THEN 1 ELSE 0 END) AS c FROM ("
        "  SELECT b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS rem "
        "  FROM inventory_boxes b WHERE b.place_id = ? AND (b.disabled IS NULL OR b.disabled = 0)"
        ")",
        (place_id,),
    ).fetchone()
    return float(row[0] or 0), int(row[1] or 0)


def _stock_by_product(conn, place_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT COALESCE(pr.code, b.product_code) AS code, "
        "SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS qty "
        "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
        "WHERE b.place_id = ? AND (b.disabled IS NULL OR b.disabled = 0) "
        "GROUP BY code HAVING qty > 0.0001 ORDER BY qty DESC",
        (place_id,),
    ).fetchall()
    return [{"code": r[0], "qty": round(float(r[1] or 0), 3)} for r in rows]


def _unit_map(conn, codes: set) -> dict:
    """mã SP → đơn vị đếm (cây/gói…) để hiện sau số lượng. Fallback '' khi không rõ."""
    codes = {c for c in codes if c}
    if not codes:
        return {}
    q = "SELECT code, COALESCE(unit,'') FROM products WHERE code IN (%s)" % ",".join("?" * len(codes))
    return {r[0]: (r[1] or "") for r in conn.execute(q, tuple(sorted(codes))).fetchall()}


def _current_boxes(conn, place_id: int) -> list[dict]:
    """Thùng HIỆN CÓ ở kho (đủ field cho BoxLabelGrid + dựng lại lịch sử box set)."""
    rows = conn.execute(
        "SELECT b.id, b.box_code, COALESCE(pr.code, b.product_code) AS product_code, b.quantity, "
        "b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS remaining, "
        "COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS allocated, "
        "COALESCE(pr.unit,'cây') AS product_unit, b.note "
        "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
        "WHERE b.place_id = ? AND (b.disabled IS NULL OR b.disabled = 0)",
        (place_id,),
    ).fetchall()
    return [{"id": r["id"], "box_code": r["box_code"], "product_code": r["product_code"],
             "quantity": float(r["quantity"] or 0), "remaining": float(r["remaining"] or 0),
             "allocated": float(r["allocated"] or 0), "product_unit": r["product_unit"],
             "note": r["note"], "disabled": False} for r in rows]


def place_timeline(place_id: int) -> dict:
    conn = _get_connection()
    try:
        prow = conn.execute("SELECT name FROM inventory_places WHERE id = ?", (place_id,)).fetchone()
        if not prow:
            return {"ok": False, "error": "Không tìm thấy vị trí"}
        current, box_count = _place_stock(conn, place_id)
        rows = conn.execute(
            "SELECT ts, actor_id, action, payload_json FROM audit_events "
            "WHERE scope = 'place' AND thread_id = ? AND action IN (%s) "
            "ORDER BY id DESC LIMIT ?" % ",".join("?" * len(_INV_ACTIONS)),
            (place_id, *sorted(_INV_ACTIONS), _CAP),
        ).fetchall()
        items = []
        running = current
        names = _load_names()   # username → tên hiển thị (Thảo, Duy…)
        for r in rows:
            act = r["action"]
            try:
                p = json.loads(r["payload_json"] or "{}")
                p = p if isinstance(p, dict) else {}
            except Exception:
                p = {}
            delta = _delta(act, p)
            pc = p.get("product_code") or ""
            bn = _boxnum(p.get("box_code"))
            items.append({
                "ts": _epoch(r["ts"]), "at": r["ts"], "dir": "in" if act in _DIR_IN else "out",
                "kind": act.replace("box.", ""), "reason": _REASON.get(act, ""), "product_code": pc,
                "box_id": p.get("box_id"), "box_code": p.get("box_code"), "box_num": bn,
                "quantity": p.get("quantity"), "delta": round(delta, 3), "amount": round(abs(delta), 3),
                # chi tiết thêm cho UI: tồn thùng SAU biến động, đơn (xuất/thu), thùng chuyển sang/nhận
                "remaining": p.get("remaining"), "order_thread_id": p.get("order_thread_id"),
                "order_text": p.get("order_text"), "peer_box": _boxnum(p.get("to_box") or p.get("from_box")),
                "from_name": p.get("from_name"), "to_name": p.get("to_name"),   # kho nguồn/đích khi chuyển
                "total_after": round(running, 3), "actor": _actor_display(r["actor_id"], names),
            })
            running -= delta
        umap = _unit_map(conn, {i["product_code"] for i in items})
        for i in items:
            i["unit"] = umap.get(i["product_code"], "")
        return {"ok": True, "place": {"id": place_id, "name": prow[0]},
                "current_total": round(current, 3), "box_count": box_count,
                "current_by_product": _stock_by_product(conn, place_id),
                "current_boxes": _current_boxes(conn, place_id),
                "items": items, "truncated": len(rows) >= _CAP}
    finally:
        conn.close()


async def place_timeline_handler(request: web.Request):
    try:
        place_id = int(request.match_info.get("place_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "place_id không hợp lệ"}, status=400)
    data = await asyncio.to_thread(place_timeline, place_id)
    return web.json_response(data, status=200 if data.get("ok") else 404)
