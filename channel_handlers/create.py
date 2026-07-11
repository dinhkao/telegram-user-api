"""Tạo đơn từ 1 tin #don_hang → forum topic + row đơn (flow_version 2).

Lõi dùng chung cho 2 nguồn:
  - listener channel_handlers/register.py  (tin gõ tay trên Telegram — incoming)
  - server_app/order_api_create.py         (đơn tạo từ webapp — tự đăng vào kênh)

Vì Telethon KHÔNG phát NewMessage cho tin do CHÍNH client gửi, đường web phải
gọi thẳng process_new_order(client, sent) thay vì trông chờ listener. Idempotent
theo message_id (đã có đơn cho tin này → trả thread_id cũ, không tạo topic trùng).

Nối: order_db (_create_order/_get_connection/_update_order_json_field), .config,
.text, .parse, server_app.realtime, server_app.fcm.
"""
from __future__ import annotations

import logging

from telethon.tl.functions.messages import CreateForumTopicRequest, UpdatePinnedMessageRequest

from order_db import _create_order, _get_connection, _update_order_json_field

from .config import ORDER_GROUP_ID, CHANNEL_DON_HANG_MOI, build_firebase_key, build_new_order
from .parse import auto_parse
from .text import escape_to_backslash_n, extract_thread_id, normalize_text, should_skip_message, topic_name_from_text

log = logging.getLogger("channel_handler")


async def firebase_sync(firebase_key, thread_id, message_id, order):
    return


async def pin_and_update(client, conn, thread_id, pin_msg_id):
    try:
        peer = await client.get_input_entity(ORDER_GROUP_ID)
        await client(UpdatePinnedMessageRequest(peer=peer, id=pin_msg_id, unpin=False))
    except Exception as e:
        log.warning("Pin message failed for thread=%d: %s", thread_id, e)
    _update_order_json_field(conn, thread_id, "$.pinMessageID", pin_msg_id)


def _existing_thread(conn, message_id: int) -> int | None:
    row = conn.execute(
        "SELECT thread_id FROM orders WHERE message_id = ? AND channel_id = ? "
        "AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 1",
        (message_id, CHANNEL_DON_HANG_MOI),
    ).fetchone()
    return int(row[0]) if row else None


async def process_new_order(client, msg, *, web_actor=None) -> int | None:
    """1 tin #don_hang → topic + đơn. Trả thread_id (None nếu bỏ qua/lỗi).

    Dùng cho cả listener lẫn webapp. An toàn gọi 2 lần cho cùng message_id
    (idempotent) — không tạo topic/đơn trùng. `web_actor` = username webapp khi tạo
    từ web (để ghi NGƯỜI TẠO); None → lấy người đăng #don_hang từ msg.sender_id."""
    if should_skip_message(msg):
        return None
    conn = _get_connection()
    existing = _existing_thread(conn, msg.id)
    if existing is not None:
        return existing

    log.info("New order from channel: msg_id=%d", msg.id)
    order_text = normalize_text(msg.text)
    text_raw = escape_to_backslash_n(order_text)
    topic_name = topic_name_from_text(order_text)
    firebase_key = build_firebase_key(msg.id)
    try:
        peer = await client.get_input_entity(ORDER_GROUP_ID)
        result = await client(CreateForumTopicRequest(peer=peer, title=topic_name, random_id=msg.id))
    except Exception as e:
        log.error("Failed to create forum topic for msg_id=%d: %s", msg.id, e)
        return None
    thread_id = extract_thread_id(result)
    if not thread_id:
        log.error("Could not extract thread_id from CreateForumTopic result for msg_id=%d", msg.id)
        return None

    # NGƯỜI TẠO đơn: web → username webapp; telegram → người đăng #don_hang (sender_id).
    # (web gửi tin bằng tài khoản bot nên sender_id vô nghĩa → phải dùng web_actor.)
    cr_type, cr_id, cr_name = "system", None, ""
    if web_actor:
        cr_type, cr_id = "web_user", str(web_actor)
        try:
            from user_store import get_user
            u = get_user(str(web_actor))
            cr_name = (u.get("display_name") if u else "") or str(web_actor)
        except Exception:
            cr_name = str(web_actor)
    else:
        sid = getattr(msg, "sender_id", None)
        if sid:
            cr_type, cr_id = "tg_user", str(sid)
            try:
                from server_app.order_api_common import resolve_name
                cr_name = await resolve_name(sid) or ""
            except Exception:
                cr_name = ""

    new_order = build_new_order(order_text, text_raw, thread_id, firebase_key, msg.id)
    if cr_name:
        new_order["created_by"] = cr_name          # hiện thẳng ở đầu OrderDetail
    if cr_id:
        new_order["created_by_id"] = cr_id
        new_order["created_by_type"] = cr_type
    _create_order(conn, firebase_key, thread_id, CHANNEL_DON_HANG_MOI, msg.id, new_order)
    client.loop.create_task(firebase_sync(firebase_key, thread_id, msg.id, new_order))
    # Log lịch sử thao tác: tạo đơn (hiện trong Lịch sử thao tác của đơn), kèm người tạo
    from audit_log import async_log_event
    client.loop.create_task(async_log_event(
        "order.created", scope="order", thread_id=thread_id,
        actor_type=cr_type, actor_id=cr_id, source="order.created", payload={"message_id": msg.id}))
    from server_app.realtime import emit_orders_changed
    emit_orders_changed()  # đơn mới → dashboard refetch (chạy nền)
    # push_bg (KHÔNG notify_bg): vừa GHI notification-center row + realtime, vừa push FCM —
    # để đơn mới hiện trong chuông 🔔 in-app (notify_bg cũ chỉ đẩy FCM, không ghi row).
    from server_app.notify import push_bg
    push_bg("🆕 Đơn hàng mới", (order_text or "").strip()[:120], {"thread_id": str(thread_id), "type": "order"})
    try:
        sent = await client.send_message(ORDER_GROUP_ID, msg.text, reply_to=thread_id)
        pin_msg_id = sent.id
    except Exception as e:
        log.warning("Failed to send welcome message for thread=%d: %s", thread_id, e)
        pin_msg_id = None
    if pin_msg_id:
        client.loop.create_task(pin_and_update(client, conn, thread_id, pin_msg_id))
    client.loop.create_task(auto_parse(client, conn, thread_id, msg.text))
    return thread_id
