"""Timeline biến động của 1 VỊ TRÍ KHO — GET /api/places/{id}/timeline.

Đọc audit_events scope='place' (ghi bởi server_app/inventory_audit), gắn nhãn +
chi tiết như lịch sử (entity_history._inv_entry), tính DELTA (+nhập / −xuất) và
TỒN KHO CHẠY (total_after) bằng cách lấy tồn HIỆN TẠI của kho rồi đi ngược thời
gian trừ dần từng biến động — làm "sổ kho" cho timeline (rail tồn giống rail nợ
của customer feed). Best-effort: bản ghi cũ trước khi có tracking → tồn có thể lệch.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from aiohttp import web

from order_db import _get_connection
from server_app.entity_history import _INV_ACTIONS, _inv_entry, _load_names
from server_app.order_history import _actor_display

_CAP = 500   # số biến động tối đa dựng lại (đủ cho 1 timeline; cũ hơn hiếm cần)


def _delta(action: str, p: dict) -> float:
    """Ảnh hưởng của 1 biến động lên TỒN (Σ remaining) của kho — dấu + (vào) / − (ra)."""
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


def _place_stock(conn, place_id: int) -> tuple[float, int]:
    """(tổng tồn hiện tại = Σ remaining, số thùng còn hiệu lực) của kho."""
    row = conn.execute(
        "SELECT COALESCE(SUM(b.quantity - COALESCE("
        "(SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)),0) AS rem, "
        "COUNT(*) AS c FROM inventory_boxes b "
        "WHERE b.place_id = ? AND (b.disabled IS NULL OR b.disabled = 0)",
        (place_id,),
    ).fetchone()
    return float(row[0] or 0), int(row[1] or 0)


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
        names = _load_names()
        items = []
        running = current   # đi từ MỚI → CŨ: total_after của mốc mới nhất = tồn hiện tại
        for r in rows:
            act = r["action"]
            try:
                p = json.loads(r["payload_json"] or "{}")
                p = p if isinstance(p, dict) else {}
            except Exception:
                p = {}
            ent = _inv_entry(act, "place", p)
            if not ent:
                continue
            delta = _delta(act, p)
            items.append({
                "ts": _epoch(r["ts"]), "at": r["ts"], "kind": act.replace("box.", ""),
                "action": ent[0], "detail": ent[1], "delta": round(delta, 3),
                "total_after": round(running, 3), "actor": _actor_display(r["actor_id"], names),
                "order_thread_id": p.get("order_thread_id"), "order_text": p.get("order_text"),
            })
            running -= delta   # lùi 1 bước: tồn TRƯỚC mốc này
        return {"ok": True, "place": {"id": place_id, "name": prow[0]},
                "current_total": round(current, 3), "box_count": box_count,
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
