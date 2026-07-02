from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection, clear_task_status, get_order_by_thread_id, set_task_status

from server_app.order_api_common import refresh_order_bg, send_task_notification
from server_app import state
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")


def _make_task_handler(task_type: str):
    async def handler(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        body["type"] = task_type
        if not body.get("user_id") and request.get("web_user"):
            body["user_id"] = request["web_user"]
        return await api_task_handler_impl(body)
    return handler


async def api_task_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    if not body.get("user_id") and request.get("web_user"):
        body["user_id"] = request["web_user"]
    return await api_task_handler_impl(body)


async def api_task_handler_impl(body: dict):
    thread_id, task_type, user_id, note = body.get("thread_id"), body.get("type"), body.get("user_id"), (body.get("note") or "").strip()
    done = body.get("done") if "done" in body else True
    if not thread_id or not task_type:
        return web.json_response({"ok": False, "error": "Missing thread_id or type"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    internal_type = {"soan": "soan_hang", "ban": "ban_hd", "giao": "giao_hang", "nop": "nop_tien", "nop-tien": "nop_tien"}.get(task_type, task_type)
    task_names = {"soan_hang": "soạn hàng", "ban_hd": "bán HĐ", "giao_hang": "giao hàng", "nop_tien": "nộp tiền"}
    set_task_status(conn, thread_id, internal_type, user_id, done=done, note=note)
    if internal_type == "giao_hang":
        from nop_tien_reminder import start_reminder, stop_reminder
        if done:
            start_reminder(thread_id)
        else:
            stop_reminder(thread_id)
    actor = "Hệ thống"
    if isinstance(user_id, str) and user_id and not user_id.isdigit():
        actor = user_id   # web user (username) — không tra Telegram entity
    elif user_id:
        try:
            entity = await state._client.get_entity(user_id)
            actor = entity.first_name or str(user_id)
        except Exception:
            actor = str(user_id)
    msg = f"{actor} đánh dấu nộp tiền" + (f" = {note}" if internal_type == "nop_tien" and done is False and note else "") if internal_type == "nop_tien" and done is False else f"{actor} nộp tiền ({note})" if internal_type == "nop_tien" and note else f"{actor} {task_names.get(internal_type, internal_type)}"
    spawn_tracked("task.notification", send_task_notification(thread_id, msg), {"thread_id": thread_id, "task": internal_type})
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    return web.json_response({"ok": True, "task": internal_type})


async def api_task_status_clear_handler(request: web.Request):
    thread_id_str = request.match_info.get("id", "")
    if not thread_id_str:
        return web.json_response({"ok": False, "error": "Missing thread ID"}, status=400)
    try:
        thread_id = int(thread_id_str)
    except ValueError:
        return web.json_response({"ok": False, "error": "Invalid thread ID"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    task_type, user_id = (body.get("type") or "").strip(), body.get("user_id")
    conn = _get_connection()
    if not clear_task_status(conn, thread_id, task_type, user_id):
        return web.json_response({"ok": False, "error": "Order not found or clear failed"}, status=404)
    if task_type == "giao_hang":
        from nop_tien_reminder import stop_reminder
        stop_reminder(thread_id)
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    spawn_tracked("task.clear_notification", send_task_notification(thread_id, f"🧹 Đã huỷ: { {'soan_hang':'soạn hàng','ban_hd':'bán HĐ','giao_hang':'giao hàng','nop_tien':'nộp tiền','nhan_tien':'nhận tiền'}.get(task_type, task_type) }"), {"thread_id": thread_id, "task": task_type})
    return web.json_response({"ok": True, "cleared": [task_type] if task_type else []})
