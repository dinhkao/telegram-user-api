from __future__ import annotations

import logging

from telethon import events
from telethon.tl.types import MessageService

from order_db import get_customer_by_key, get_order_by_thread_id
from print_service import execute_print_giao

from .common import _extract_thread_id, _resolve_name

log = logging.getLogger("order_commands_v3")


def register_print_handlers(client, db_conn):
    @client.on(events.NewMessage(chats=int(__import__("os").getenv("ORDER_GROUP_ID", "-1002124542200"))))
    async def on_print(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip() != "print":
            return
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            return
        user_id = getattr(msg, "sender_id", None)

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        invoice_id = order.get("kiotvietInvoiceID")
        if not invoice_id:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có hóa đơn KiotViet. Dùng lệnh `tao hd` trước.", reply_to=msg.id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        customer_name = "Khách hàng"
        if kh_id_fb:
            customer = get_customer_by_key(db_conn, str(kh_id_fb))
            if customer:
                customer_name = customer.get("name", "Khách hàng")

        printed_by = await _resolve_name(client, user_id) if user_id else "Hệ thống"
        proc_msg = await client.send_message(msg.chat_id, "⏳ Đang in phiếu giao hàng......", reply_to=msg.id)

        try:
            result = await execute_print_giao(db_conn, order, user_id)
            if result.get("error"):
                raise RuntimeError(result["error"])
            await client.edit_message(
                msg.chat_id,
                proc_msg.id,
                f"🖨️ {printed_by} đã in 2 hóa đơn (không QR) và Phiếu giao hàng",
            )
        except Exception as e:
            log.error("Print failed: %s", e, exc_info=True)
            await client.edit_message(
                msg.chat_id,
                proc_msg.id,
                f"❌ Lỗi in phiếu: {e}",
            )
