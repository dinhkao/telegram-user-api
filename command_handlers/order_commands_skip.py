from __future__ import annotations

import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import set_task_status

from .order_commands_common import ORDER_GROUP_ID, SKIP_COMMANDS, notify_refresh
from .thread_utils import extract_thread_id


def register_order_commands_skip(client, db_conn):
    skip_re = re.compile(rf"^(?:{'|'.join(re.escape(c) for c in SKIP_COMMANDS)})$", re.IGNORECASE)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_skip(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        m = skip_re.match((msg.text or "").strip())
        if not m:
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được thread_id.", reply_to=msg.id)
            return
        if set_task_status(db_conn, thread_id, SKIP_COMMANDS[m.group(0).lower()], getattr(msg, "sender_id", None), skip=True):
            await client.send_message(msg.chat.id, "🔘 Đã bỏ qua Nộp tiền", reply_to=msg.id)
            notify_refresh(client, db_conn, thread_id)
        else:
            await client.send_message(msg.chat_id, "❌ Không thể bỏ qua (lỗi không xác định).", reply_to=msg.id)

