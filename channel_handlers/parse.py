from __future__ import annotations

import logging

from order_db import get_order_by_thread_id
from product_db import freeze_invoice_cost_prices, get_all_products

from .config import ORDER_GROUP_ID
from .notify import build_auto_parse_notification
from .render import render_channel_post

log = logging.getLogger("channel_handler")


async def auto_parse(client, conn, thread_id: int, text: str):
    try:
        from order_db import _update_order_json_field, detect_customer_free_text, parse_invoice_free_text
        from picking_sheet import generate_picking_sheet
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            log.warning("auto-parse: order not found thread=%d", thread_id)
            return
        all_products = get_all_products(conn)
        detection = detect_customer_free_text(conn, text)
        assigned_cust = None
        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        if detection.get("autoAssign"):
            assigned_cust = detection["autoAssign"]
            kh_id_fb = assigned_cust["customerID"]
            _update_order_json_field(conn, thread_id, "$.khach_hang_id", assigned_cust["customerID"])
            _update_order_json_field(conn, thread_id, "$.customer_name", assigned_cust["customerName"])
            from order_db import touch_customer_last_order
            touch_customer_last_order(conn, kh_id_fb)
        invoice = parse_invoice_free_text(conn, text, kh_id_fb, _all_products=all_products)
        if invoice:
            _update_order_json_field(conn, thread_id, "$.invoice", freeze_invoice_cost_prices(conn, invoice))
        log.info("auto-parse: thread=%d items=%d assigned=%s", thread_id, len(invoice) if invoice else 0, assigned_cust["customerName"] if assigned_cust else "none")
        lines = build_auto_parse_notification(invoice, assigned_cust, detection)
        if lines:
            async def _send_notif():
                try:
                    await client.send_message(ORDER_GROUP_ID, "\n".join(lines), reply_to=thread_id, parse_mode="html")
                except Exception as e:
                    log.warning("auto-parse notification failed: %s", e)
            client.loop.create_task(_send_notif())
        order = get_order_by_thread_id(conn, thread_id)
        if order:
            row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
            if row and row["channel_id"] and row["message_id"]:
                await render_channel_post(client, conn, thread_id, row["message_id"], order)
        if invoice:
            try:
                await generate_picking_sheet(client, conn, thread_id)
            except Exception as e:
                log.warning("picking sheet generation failed for thread=%d: %s", thread_id, e)
    except Exception as e:
        log.warning("auto-parse failed for thread=%d: %s", thread_id, e)
