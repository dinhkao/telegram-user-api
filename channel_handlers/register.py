from __future__ import annotations

import logging

from telethon import events
from telethon.tl.functions.messages import CreateForumTopicRequest, UpdatePinnedMessageRequest

from order_db import _create_order, _get_connection, _update_order_json_field

from .config import ORDER_GROUP_ID, CHANNEL_DON_HANG_MOI, build_firebase_key, build_new_order, now_iso
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


def register(client):
    @client.on(events.NewMessage(chats=CHANNEL_DON_HANG_MOI))
    async def on_channel_post(event):
        msg = event.message
        if should_skip_message(msg):
            return
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
            return
        thread_id = extract_thread_id(result)
        if not thread_id:
            log.error("Could not extract thread_id from CreateForumTopic result for msg_id=%d", msg.id)
            return
        new_order = build_new_order(order_text, text_raw, thread_id, firebase_key, msg.id)
        conn = _get_connection()
        _create_order(conn, firebase_key, thread_id, CHANNEL_DON_HANG_MOI, msg.id, new_order)
        client.loop.create_task(firebase_sync(firebase_key, thread_id, msg.id, new_order))
        from server_app.realtime import emit_orders_changed
        emit_orders_changed()  # đơn mới → dashboard refetch (chạy nền)
        from server_app.fcm import notify_bg
        notify_bg("🆕 Đơn hàng mới", (order_text or "").strip()[:120], {"thread_id": str(thread_id)})
        try:
            sent = await client.send_message(ORDER_GROUP_ID, msg.text, reply_to=thread_id)
            pin_msg_id = sent.id
        except Exception as e:
            log.warning("Failed to send welcome message for thread=%d: %s", thread_id, e)
            pin_msg_id = None
        if pin_msg_id:
            client.loop.create_task(pin_and_update(client, conn, thread_id, pin_msg_id))
        client.loop.create_task(auto_parse(client, conn, thread_id, msg.text))
