from __future__ import annotations

import asyncio
import logging
import os

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, _save_order, detect_customer_free_text, get_order_by_thread_id

from .order_commands_v2_common import refresh_main_msg
from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_order_commands_v2_detect_customer(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect_customer(event):
        msg = event.message
        if isinstance(msg, MessageService) or (msg.text or "").strip().lower() != "detect customer":
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        order_text = order.get("text") or order.get("text_raw") or ""
        if not order_text:
            await client.send_message(msg.chat_id, "❌ Đơn hàng này không có nội dung để phân tích.", reply_to=msg.id)
            return
        detection = detect_customer_free_text(db_conn, order_text)
        if not detection["matches"]:
            await client.send_message(msg.chat_id, "❌ Chưa có patterns trong database khách hàng hoặc không tìm thấy khách hàng phù hợp.", reply_to=msg.id)
            return
        if detection["autoAssign"]:
            cust = detection["autoAssign"]
            order["khach_hang_id"], order["customer_name"] = cust["customerID"], cust["customerName"]
            _save_order(db_conn, thread_id, order)
            from order_db import touch_customer_last_order
            touch_customer_last_order(db_conn, cust["customerID"])
            if order.get("channel_id") and order.get("message_id"):
                asyncio.ensure_future(refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"]))
            reply = f"👤 <b>Đã gán:</b> {cust['customerName']}\n🎯 Mẫu: \"{cust['bestMatchedPattern']}\" ({cust['score']}%)\n\n✅ Đã lưu vào SQLite. Bấm 'Xem hóa đơn' để kiểm tra."
        else:
            lines = [f"🔍 <b>Tìm thấy {len(detection['matches'])} khách hàng tiềm năng:</b>\n"]
            for i, m in enumerate(detection["matches"][:5], 1):
                lines.append(f"  {i}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
            reply = "\n".join(lines)
        await client.send_message(msg.chat_id, reply, reply_to=msg.id, parse_mode="html")

