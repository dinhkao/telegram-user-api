from __future__ import annotations

import asyncio
import logging
import os

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, _save_order, detect_customer_free_text, get_customer_price_list, get_order_by_thread_id, parse_invoice_free_text
from product_db import freeze_invoice_cost_prices

from .order_commands_v2_common import refresh_main_msg
from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_order_commands_v2_detect_all(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect(event):
        msg = event.message
        if isinstance(msg, MessageService) or (msg.text or "").strip().lower() != "detect":
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
        kh_id = order.get("khach_hang_id") or order.get("khID")
        lines = []
        if detection["autoAssign"]:
            cust = detection["autoAssign"]
            order["khach_hang_id"], order["customer_name"] = cust["customerID"], cust["customerName"]
            kh_id = cust["customerID"]
            lines += [f"👤 <b>Đã gán:</b> {cust['customerName']} ({cust['score']}%)", f"🎯 Mẫu: \"{cust['bestMatchedPattern']}\""]
        elif detection["matches"]:
            lines.append("🔍 <b>Khách hàng có thể:</b>")
            for i, m in enumerate(detection["matches"][:3], 1):
                lines.append(f"  {i}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
        else:
            lines.append("👤 Không tìm thấy khách hàng phù hợp.")
        invoice = parse_invoice_free_text(db_conn, order_text, kh_id)
        if kh_id and get_customer_price_list(db_conn, kh_id):
            invoice = parse_invoice_free_text(db_conn, order_text, kh_id)
        if invoice:
            order["invoice"] = freeze_invoice_cost_prices(db_conn, invoice)
            total = 0
            lines.append(f"\n🎯 <b>Tìm thấy {len(invoice)} sản phẩm:</b>")
            for item in invoice:
                sub = int(item.get("sl", 0) or 0) * int(item.get("price", 0) or 0)
                total += sub
                lines.append(f"• <b>{item.get('sp', '?')}</b> x{item.get('sl', 0)} @ {int(item.get('price', 0) or 0):,}đ = <b>{sub:,}đ</b>")
            lines.append(f"\n💰 <b>Tổng cộng: {total:,}đ</b>")
        else:
            lines.append("\n🎯 Không tìm thấy sản phẩm nào.")
        _save_order(db_conn, thread_id, order)
        if order.get("channel_id") and order.get("message_id"):
            asyncio.ensure_future(refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"]))
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

