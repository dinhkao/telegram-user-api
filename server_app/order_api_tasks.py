from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection, clear_task_status, get_order_by_thread_id, set_task_status

from server_app.order_api_common import apply_web_actor, refresh_order_bg, resolve_name, send_task_notification
from server_app import state
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")

# Các task hợp lệ (khóa trong order JSON) — chặn type lạ làm bẩn blob qua HTTP.
_VALID_TASK_TYPES = {"soan_hang", "ban_hd", "giao_hang", "nop_tien", "nhan_tien"}
_TASK_ALIASES = {"soan": "soan_hang", "ban": "ban_hd", "giao": "giao_hang", "nop": "nop_tien", "nop-tien": "nop_tien"}


def _make_task_handler(task_type: str):
    async def handler(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        body["type"] = task_type
        apply_web_actor(request, body)
        return await api_task_handler_impl(body)
    return handler


async def _deny_if_nhan_tien_not_office(request, task_type_raw):
    """Task 'nhận tiền' chỉ văn phòng (admin/van_phong) được đánh dấu/huỷ.
    Trả về response 403 nếu bị chặn, None nếu cho qua."""
    internal = _TASK_ALIASES.get(task_type_raw, task_type_raw)
    if internal == "nhan_tien":
        from server_app.order_api_common import is_office_request
        if not await is_office_request(request):
            return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được đánh dấu nhận tiền"}, status=403)
    return None


async def api_task_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    deny = await _deny_if_nhan_tien_not_office(request, body.get("type"))
    if deny:
        return deny
    apply_web_actor(request, body)
    return await api_task_handler_impl(body)


async def api_task_handler_impl(body: dict):
    thread_id, task_type, user_id, note = body.get("thread_id"), body.get("type"), body.get("user_id"), (body.get("note") or "").strip()
    done = body.get("done") if "done" in body else True
    if not thread_id or not task_type:
        return web.json_response({"ok": False, "error": "Missing thread_id or type"}, status=400)
    internal_type = _TASK_ALIASES.get(task_type, task_type)
    if internal_type not in _VALID_TASK_TYPES:
        return web.json_response({"ok": False, "error": f"Loại task không hợp lệ: {task_type}"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    task_names = {"soan_hang": "soạn hàng", "ban_hd": "bán HĐ", "giao_hang": "giao hàng", "nop_tien": "nộp tiền", "nhan_tien": "nhận tiền"}
    set_task_status(conn, thread_id, internal_type, user_id, done=done, note=note)
    if internal_type == "giao_hang":
        from nop_tien_reminder import start_reminder, stop_reminder
        if done:
            start_reminder(thread_id)
        else:
            stop_reminder(thread_id)
    actor = await resolve_name(user_id) if user_id else "Hệ thống"
    msg = f"{actor} đánh dấu nộp tiền" + (f" = {note}" if internal_type == "nop_tien" and done is False and note else "") if internal_type == "nop_tien" and done is False else f"{actor} nộp tiền ({note})" if internal_type == "nop_tien" and note else f"{actor} {task_names.get(internal_type, internal_type)}"
    if int(thread_id) > 0:   # đơn web (thread_id âm) không có topic Telegram — khỏi gửi
        spawn_tracked("task.notification", send_task_notification(thread_id, msg), {"thread_id": thread_id, "task": internal_type})
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    else:   # đơn web-only (không topic) — vẫn phải phát realtime cho webapp
        from server_app.realtime import emit_order_changed
        emit_order_changed(thread_id)
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
    deny = await _deny_if_nhan_tien_not_office(request, (body.get("type") or "").strip())
    if deny:
        return deny
    apply_web_actor(request, body)
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
    else:   # đơn web-only — vẫn phát realtime
        from server_app.realtime import emit_order_changed
        emit_order_changed(thread_id)
    if thread_id > 0:   # đơn web không có topic Telegram
        spawn_tracked("task.clear_notification", send_task_notification(thread_id, f"🧹 Đã huỷ: { {'soan_hang':'soạn hàng','ban_hd':'bán HĐ','giao_hang':'giao hàng','nop_tien':'nộp tiền','nhan_tien':'nhận tiền'}.get(task_type, task_type) }"), {"thread_id": thread_id, "task": task_type})
    return web.json_response({"ok": True, "cleared": [task_type] if task_type else []})
