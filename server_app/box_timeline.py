"""Timeline biến động của 1 THÙNG — GET /api/inventory/box/{id}/timeline.

Đọc audit_events scope='box' (ghi bởi server_app/inventory_audit): nhập mới / xuất
cho đơn / thu về / chuyển kho / chuyển hàng sang-nhận thùng khác. Mỗi item kèm TỒN
CỦA THÙNG sau biến động (payload 'remaining') + delta để client dựng "còn X→Y".
Nối: inventory_store.get_box, product_store (đơn vị), server_app.order_history (tên actor).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web

from order_db import _get_connection
from server_app.order_history import _actor_display, _load_names

_CAP = 400
_ACTIONS = ("box.created", "box.allocated", "box.released", "box.moved",
            "box.transfer_out", "box.transfer_in", "box.consumed", "box.disposed", "box.disposal_released")
_DIR_IN = {"box.created", "box.released", "box.transfer_in", "box.disposal_released"}
_REASON = {"box.created": "nhập mới", "box.allocated": "xuất cho đơn", "box.released": "thu về từ đơn",
           "box.moved": "chuyển kho", "box.transfer_out": "chuyển sang thùng khác",
           "box.transfer_in": "nhận từ thùng khác", "box.consumed": "tiêu hao đóng gói",
           "box.disposed": "xuất hủy", "box.disposal_released": "hoàn xuất hủy"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _epoch(ts: str) -> int:
    try:
        return int(datetime.fromisoformat((ts or "").replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def _boxnum(code) -> str:
    s = str(code or "")
    return s.split("-")[-1] or s


def _delta(action: str, p: dict) -> float:
    """Ảnh hưởng lên TỒN của thùng — + (vào) / − (ra)."""
    q = _num(p.get("quantity"))
    taken = _num(p.get("taken"))
    return {
        "box.created": q, "box.released": taken, "box.transfer_in": q,
        "box.allocated": -taken, "box.transfer_out": -q, "box.moved": 0.0,
        "box.consumed": -taken, "box.disposed": -taken, "box.disposal_released": taken,
    }.get(action, 0.0)


def box_timeline(box_id: int) -> dict:
    from inventory_store import get_box
    conn = _get_connection()
    try:
        b = get_box(conn, box_id)
        if not b:
            return {"ok": False, "error": "Không tìm thấy thùng"}
        used = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?", (box_id,)
        ).fetchone()[0]
        remaining = float(b.get("quantity") or 0) - float(used or 0)
        rows = conn.execute(
            "SELECT ts, actor_id, action, payload_json FROM audit_events "
            "WHERE scope = 'box' AND thread_id = ? AND action IN (%s) "
            "ORDER BY id DESC LIMIT ?" % ",".join("?" * len(_ACTIONS)),
            (box_id, *_ACTIONS, _CAP),
        ).fetchall()
        names = _load_names()
        unit = b.get("product_unit") or "cây"
        items = []
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
                "dir": "in" if act in _DIR_IN else ("neutral" if act == "box.moved" else "out"),
                "kind": act.replace("box.", ""), "reason": _REASON.get(act, ""),
                "quantity": p.get("quantity"), "taken": p.get("taken"),
                "amount": round(abs(delta), 3), "delta": round(delta, 3),
                "remaining": p.get("remaining"),   # tồn của THÙNG sau biến động
                "order_thread_id": p.get("order_thread_id"), "order_text": p.get("order_text"),
                "peer_box": _boxnum(p.get("to_box") or p.get("from_box") or p.get("to_code") or p.get("from_code")),
                "from_name": p.get("from_name"), "to_name": p.get("to_name"),
                "target_code": p.get("target_code"), "slip_id": p.get("slip_id"),   # tiêu hao đóng gói
                "disposal_id": p.get("disposal_id"), "disposal_reason": p.get("disposal_reason"),
                "unit": unit, "actor": _actor_display(r["actor_id"], names),
            })
        return {"ok": True, "items": items, "truncated": len(rows) >= _CAP,
                "box": {"id": b.get("id"), "box_code": b.get("box_code"), "box_num": _boxnum(b.get("box_code")),
                        "product_code": b.get("product_code"), "unit": unit,
                        "quantity": float(b.get("quantity") or 0), "remaining": round(remaining, 3),
                        "place_name": b.get("place_name"), "source_thread_id": b.get("source_thread_id")}}
    finally:
        conn.close()


async def box_timeline_handler(request: web.Request):
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    data = await asyncio.to_thread(box_timeline, box_id)
    return web.json_response(data, status=200 if data.get("ok") else 404)
