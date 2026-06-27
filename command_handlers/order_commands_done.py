from __future__ import annotations

import re

from telethon import Button, events
from telethon.tl.types import MessageService

from order_db import get_order_by_thread_id, set_task_status

from .order_commands_common import ORDER_GROUP_ID, TASK_DONE_COMMANDS, notify_refresh, resolve_user_name
from .thread_utils import extract_thread_id


def register_order_commands_done(client, db_conn):
    done_re = re.compile(rf"^(?:{'|'.join(re.escape(c) for c in TASK_DONE_COMMANDS)})$", re.IGNORECASE)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_done(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        m = done_re.match((msg.text or "").strip())
        if not m:
            return
        task_type, reply_text = TASK_DONE_COMMANDS[m.group(0).lower()]
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.", reply_to=msg.id)
            return
        order = get_order_by_thread_id(db_conn, thread_id)
        if order and order.get("flow_version") != 2:
            await client.send_message(msg.chat_id, "❌ Đơn hàng V1. Dùng 'migrate tasks' để chuyển sang V2 trước.", reply_to=msg.id)
            return
        sender_id = getattr(msg, "sender_id", None)
        user_name = await resolve_user_name(client, sender_id)
        if set_task_status(db_conn, thread_id, task_type, sender_id):
            if task_type == "soan_hang":
                try:
                    await client.send_message(msg.chat_id, reply_text.format(user=user_name), reply_to=msg.id, buttons=[[Button.inline("A", "soan_test_a"), Button.inline("B", "soan_test_b")]])
                except Exception:
                    pass
            else:
                await client.send_message(msg.chat_id, reply_text.format(user=user_name), reply_to=msg.id)
            notify_refresh(client, db_conn, thread_id)
        else:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng hoặc lỗi cập nhật.", reply_to=msg.id)

