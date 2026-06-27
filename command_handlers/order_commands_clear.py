from __future__ import annotations

import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import clear_task_status

from .order_commands_common import CLEAR_COMMANDS, CLEAR_REPLIES, ORDER_GROUP_ID, notify_refresh
from .thread_utils import extract_thread_id


def register_order_commands_clear(client, db_conn):
    clear_re = re.compile(rf"^(?:{'|'.join(re.escape(c) for c in CLEAR_COMMANDS)})$", re.IGNORECASE)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_clear(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        m = clear_re.match((msg.text or "").strip())
        if not m:
            return
        task_type = CLEAR_COMMANDS[m.group(0).lower()]
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.", reply_to=msg.id)
            return
        if clear_task_status(db_conn, thread_id, task_type, getattr(msg, "sender_id", None)):
            await client.send_message(msg.chat_id, CLEAR_REPLIES.get(task_type, "♻️ Đã đặt lại trạng thái"), reply_to=msg.id)
            notify_refresh(client, db_conn, thread_id)
        else:
            await client.send_message(msg.chat_id, "❌ Không thể đặt lại trạng thái (lỗi không xác định).", reply_to=msg.id)

