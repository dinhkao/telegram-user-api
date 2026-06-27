from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

from firebase_png_print import ref as fb_ref
from printouts.common import queue_html_for_print
from renderers.common import esc, internal_group_id, qr_url

log = logging.getLogger("delivery_ticket")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
TASK_GROUP_ID = int(os.getenv("TASK_GROUP_ID", "-1002574612166"))
META_TO_PRINT_PATH = "meta/to_print"


def generate_delivery_ticket_html(thread_id: int, customer_name: str, order_text: str, printed_by: str = "", nop_tien_topic_url: str = "") -> str:
    order_topic_url = f"tg://privatepost?channel={internal_group_id(ORDER_GROUP_ID)}&post={thread_id}" if thread_id else ""
    qr_size = 64
    order_qr = qr_url(order_topic_url, qr_size) if order_topic_url else ""
    nop_qr = qr_url(nop_tien_topic_url, qr_size) if nop_tien_topic_url else ""
    vn_now = datetime.now(timezone(timedelta(hours=7)))
    time_label = vn_now.strftime("%H:%M:%S %d/%m/%Y")
    safe_name = esc(customer_name or "Khách hàng")
    safe_text = esc(order_text or "")
    safe_printed_by = esc(printed_by or "—")
    order_qr_html = f'''<div><div class="meta" style="text-align:right">QR: Topic Đơn hàng</div><img src="{order_qr}" width="{qr_size}" height="{qr_size}"/></div>''' if order_qr else ""
    nop_qr_html = f'''<div><div class="meta" style="text-align:right">QR: Topic Nộp tiền</div><img src="{nop_qr}" width="{qr_size}" height="{qr_size}"/></div>''' if nop_qr else ""
    return f'''<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Phiếu giao hàng {thread_id}</title>
<style>
  body {{ width: 280px; font-family: Arial, sans-serif; }}
  h1 {{ font-size: 18px; text-align:center; margin: 0 0 6px 0; }}
  .row {{ display: flex; justify-content: space-between; }}
  .label {{ font-weight: bold; }}
  .block {{ margin: 6px 0; }}
  .order-text {{ white-space: pre-wrap; word-wrap: break-word; border: 1px dashed #ccc; padding: 6px; }}
  .qrs {{ display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-top: 8px; }}
  .top-right {{ text-align: right; }}
  .bottom-right {{ text-align: right; margin-top: 8px; }}
  .meta {{ font-size: 12px; color: #333; }}
  hr {{ margin: 6px 0; }}
</style>
</head><body>
  <h1>PHIẾU GIAO HÀNG</h1>
  <div class="top-right">{order_qr_html}</div>
  <div class="block"><span class="label">Khách hàng:</span> {safe_name}</div>
  <div class="block"><span class="label">Đơn hàng:</span></div>
  <div class="order-text">{safe_text}</div>
  <div class="block meta"><span class="label">In bởi:</span> {safe_printed_by}</div>
  <div class="block meta"><span class="label">Thời gian:</span> {time_label}</div>
  <hr />
  <div class="bottom-right">
    {nop_qr_html}
  </div>
</body></html>'''


async def _enqueue_html_for_print(html: str, copies: int = 1) -> None:
    ref = fb_ref(META_TO_PRINT_PATH)
    if ref is None:
        log.warning("Firebase not configured — skipping print queue")
        return
    try:
        ok = await queue_html_for_print(ref, html, copies)
        if ok:
            log.info("Queued %d copy(ies) for printing", max(1, copies))
    except Exception as e:
        log.warning("Failed to queue for printing: %s", e)


async def print_delivery_ticket(client, thread_id: int, customer_name: str, order_text: str, printed_by: str = "", nop_tien_topic_url: str = "") -> None:
    html = generate_delivery_ticket_html(thread_id, customer_name, order_text, printed_by, nop_tien_topic_url)
    try:
        await _enqueue_html_for_print(html, copies=1)
    except Exception as e:
        log.warning("Failed to print delivery ticket: %s", e)
