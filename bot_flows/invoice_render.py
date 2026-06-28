"""bot_flows/invoice_render.py — Generate invoice HTML, send file, render PNG."""
import logging
import os
import tempfile
import time

from bot_core import config
from bot_core.utils import esc_html

log = logging.getLogger("bot.flows")


async def render_and_send_invoice(bot, event, s, invoice_id, invoice_code, customer, vat, pvc, snapshot_debt):
    """Generate invoice HTML, send as file + PNG."""
    try:
        from inhoadon import generate_invoice_html
        from kiotviet import get_invoice_detail as _get_invoice_detail
        inv_detail = _get_invoice_detail(invoice_id)
        if inv_detail:
            html = generate_invoice_html(inv_detail, snapshot_debt, {
                "expectedVAT": vat,
                "expectedPVC": pvc,
                "orderTopicUrl": f"tg://privatepost?channel={str(config.GROUP_CHAT_ID).replace('-100', '')}&post={s.thread_id}",
                "customerNameOverride": customer.get("name"),
                "disableQR": True,
            })
        else:
            html = f"<html><body><h1>Hóa đơn #{invoice_code}</h1><p>Khách: {esc_html(customer.get('name', ''))}</p></body></html>"

        fn = f"invoice_{s.thread_id}_{int(time.time())}.html"
        file_path = os.path.join(tempfile.gettempdir(), fn)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        await bot.send_file(s.chat_id, file_path,
            caption=f"🧾 Hóa đơn {invoice_code} — {customer.get('name', '')}",
            force_document=True)
        try:
            os.unlink(file_path)
        except OSError:
            pass

        try:
            from bot_core.html_to_png import render_and_send_html
            await render_and_send_html(bot, html, s.chat_id, reply_to=s.thread_id,
                caption=f"🧾 Hóa đơn {invoice_code} — {customer.get('name', '')}")
        except Exception as e:
            log.warning("Failed to render invoice PNG: %s", e)
    except Exception as e:
        log.error("Invoice HTML generation failed: %s", e)
        await bot.send_message(s.chat_id, f"✅ Đã tạo hóa đơn KiotViet: #{invoice_code} (không gửi được file HTML)")


async def refresh_order_view(s):
    """Trigger order message update via API."""
    from bot_core.utils import post_json
    from bot_flows._helpers import ORDER_API_BASE
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/refresh-view", {"thread_id": s.thread_id})
    except Exception as e:
        log.warning("refresh-view failed: %s", e)
