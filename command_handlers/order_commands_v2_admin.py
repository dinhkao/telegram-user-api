from __future__ import annotations

import logging
import os
import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, delete_all_tasks, get_all_tasks, set_order_flag, sort_tasks, migrate_tasks_to_v2

from .order_commands_v2_utils import call_final, fmt_task_list
from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_order_commands_v2_admin(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_admin(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        lower = text.lower()
        if lower == "show task":
            tasks = get_all_tasks(db_conn)
            await client.send_message(msg.chat_id, "📋 Không có task nào" if not tasks else fmt_task_list(tasks), reply_to=msg.id, parse_mode="html")
            return
        if lower == "delete all task":
            _, message = delete_all_tasks(db_conn)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
            return
        if lower == "sort tasks":
            _, message = sort_tasks(db_conn)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
            return
        if lower == "migrate tasks":
            _, message = migrate_tasks_to_v2(db_conn)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
            return
        if lower == "check tasks":
            tasks = get_all_tasks(db_conn)
            total = len(tasks)
            v2 = sum(1 for t in tasks if t.get("flow_version") == 2)
            incomplete = sum(1 for t in tasks if any(isinstance(v, dict) and not (v.get("done") or v.get("skip")) for v in t["task_status"].values()))
            await client.send_message(msg.chat_id, f"📊 <b>Thống kê task:</b>\nTổng: {total}\nV2: {v2}\nChưa xong: {incomplete}", reply_to=msg.id, parse_mode="html")
            return
        if lower == "send task notification":
            result = call_final("/api/order/send-task-notification", {"chat_id": msg.chat_id})
            await client.send_message(msg.chat_id, result.get("reply", "✅ Đã gửi thông báo") if result else "❌ Lỗi kết nối", reply_to=msg.id)
            return
        if lower in {"turn on money", "turn off money"}:
            thread_id = extract_thread_id(msg)
            if thread_id:
                await client.send_message(msg.chat_id, set_order_flag(db_conn, thread_id, "show_price", lower == "turn on money")[1], reply_to=msg.id)
            return
        if lower == "update debt":
            thread_id = extract_thread_id(msg)
            if thread_id:
                result = call_final("/api/order/update-debt", {"thread_id": thread_id})
                await client.send_message(msg.chat_id, result.get("reply", "✅ Đã cập nhật công nợ") if result else "❌ Lỗi kết nối", reply_to=msg.id)
            return
        if m := re.match(r"^date\s+(.+)$", text, re.IGNORECASE):
            thread_id = extract_thread_id(msg)
            if thread_id:
                await client.send_message(msg.chat_id, set_order_flag(db_conn, thread_id, "date_override", m.group(1).strip())[1], reply_to=msg.id)
            return
        if m := re.match(r"^time\s+(.+)$", text, re.IGNORECASE):
            thread_id = extract_thread_id(msg)
            if thread_id:
                await client.send_message(msg.chat_id, set_order_flag(db_conn, thread_id, "time_override", m.group(1).strip())[1], reply_to=msg.id)
            return
        if msg.photo or msg.video:
            thread_id = extract_thread_id(msg)
            if thread_id:
                log.debug("media: thread=%d type=%s msg_id=%d", thread_id, "photo" if msg.photo else "video", msg.id)
