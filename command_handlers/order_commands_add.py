from __future__ import annotations

import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import set_task_status

from .order_commands_common import ORDER_GROUP_ID, notify_refresh
from .thread_utils import extract_thread_id


def register_order_commands_add(client, db_conn):
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_add_xuat_hd(event):
        msg = event.message
        if isinstance(msg, MessageService) or not re.match(r"^add\s+xuat\s*hd$", (msg.text or "").strip(), re.IGNORECASE):
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được thread_id", reply_to=msg.id)
            return
        if set_task_status(db_conn, thread_id, "xuat_hd", getattr(msg, "sender_id", None), done=False):
            await client.send_message(msg.chat_id, "🆕 Đã thêm task Xuất HĐ (chưa hoàn thành)", reply_to=msg.id)
            notify_refresh(client, db_conn, thread_id)
        else:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng hoặc lỗi cập nhật.", reply_to=msg.id)

