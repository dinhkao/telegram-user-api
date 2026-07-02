from __future__ import annotations

import logging

from server_app.config import ORDER_GROUP_ID
from server_app import state
from server_app.telegram_helpers import tg_edit_message, tg_send_message
from order_html import build_order_main_message_html

log = logging.getLogger("server")


def apply_web_actor(request, body: dict, key: str = "user_id") -> None:
    """Đóng dấu user web (từ token) vào body[key] cho các endpoint mutation.

    Token luôn thắng body (chống giả mạo); body chỉ được tự khai khi CHƯA bật
    chặn auth (giai đoạn chuyển tiếp). Dùng ở mọi handler ghi có actor.
    """
    from server_app.config import WEB_AUTH_ENABLED
    web_user = request.get("web_user")
    if web_user:
        if WEB_AUTH_ENABLED or not body.get(key):
            body[key] = web_user


async def resolve_name(user_id: int) -> str:
    if isinstance(user_id, str) and user_id and not user_id.isdigit():
        return user_id   # web user (username) — không tra Telegram entity
    try:
        entity = await state._client.get_entity(user_id)
        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        if first:
            return f"{first} {last}".strip()
        username = getattr(entity, "username", "") or ""
        return f"@{username}" if username else str(user_id)
    except Exception:
        return str(user_id)


async def send_task_notification(thread_id, message):
    try:
        await tg_send_message(ORDER_GROUP_ID, message, reply_to=thread_id)
    except Exception as e:
        log.warning("Task notification failed: %s", e)


async def refresh_order_bg(conn, thread_id, channel_id, message_id):
    try:
        from order_db import get_order_by_thread_id
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        await tg_edit_message(channel_id, message_id, text=build_order_main_message_html(order, thread_id), parse_mode="html", link_preview=False)
    except Exception as e:
        log.warning("refresh order failed: thread=%s channel=%s message=%s error=%s", thread_id, channel_id, message_id, e, exc_info=True)
    # Đẩy realtime tới webapp (best-effort, không chặn refresh nếu lỗi)
    from server_app.realtime import broadcast_order_changed
    await broadcast_order_changed(thread_id)
