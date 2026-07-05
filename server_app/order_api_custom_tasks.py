"""HTTP: user-defined custom tasks on an order (add / remove the definition).

Beside the 5 default steps. Delegates to order_store.custom_tasks; toggling a
custom task's done-status goes through the normal /api/order/task path. Refreshes
the Telegram order message + emits realtime like the default task handlers.
"""
from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection
from order_store.custom_tasks import add_custom_task, remove_custom_task

from server_app.order_api_common import apply_web_actor, refresh_order_bg
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")


def _parse_thread_id(request: web.Request):
    try:
        return int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return None


async def _refresh(conn, thread_id: int):
    """Re-render the Telegram order message (which emits realtime) or, for
    web-only orders (no topic), emit realtime directly."""
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    else:
        from server_app.realtime import emit_order_changed
        emit_order_changed(thread_id)


async def add_custom_task_handler(request: web.Request):
    thread_id = _parse_thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "Invalid thread ID"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    conn = _get_connection()
    task_id = add_custom_task(conn, thread_id, body.get("label", ""), body.get("user_id"))
    if not task_id:
        return web.json_response({"ok": False, "error": "Thiếu tên việc hoặc không tìm thấy đơn"}, status=400)
    await _refresh(conn, thread_id)
    return web.json_response({"ok": True, "id": task_id})


async def remove_custom_task_handler(request: web.Request):
    thread_id = _parse_thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "Invalid thread ID"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    apply_web_actor(request, body)
    task_id = (body.get("id") or "").strip()
    if not task_id:
        return web.json_response({"ok": False, "error": "Missing task id"}, status=400)
    conn = _get_connection()
    if not remove_custom_task(conn, thread_id, task_id):
        return web.json_response({"ok": False, "error": "Order not found or remove failed"}, status=404)
    await _refresh(conn, thread_id)
    return web.json_response({"ok": True, "removed": task_id})
