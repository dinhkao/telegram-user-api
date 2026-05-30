"""delivery_ticket.py — Generate delivery ticket HTML (Phiếu giao hàng).

Mirrors Node.js DonHang.generateDeliveryTicketHTML() + printDeliveryTicket().
Generates HTML with QR codes for order topic and nộp tiền task topic.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta

from firebase_sync import _ref as fb_ref

log = logging.getLogger("delivery_ticket")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
TASK_GROUP_ID = int(os.getenv("TASK_GROUP_ID", "-1002574612166"))
META_TO_PRINT_PATH = "meta/to_print"


def _escape_html(s: str) -> str:
    """Escape HTML special characters."""
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _get_internal_group_id(group_id: int) -> str:
    """Convert Telegram group ID to internal format (remove -100 prefix)."""
    group_id_str = str(group_id)
    if group_id_str.startswith("-100"):
        return group_id_str[4:]
    return str(abs(group_id))


def _generate_qr_url(data: str, size: int = 64) -> str:
    """Generate QR code URL using external API (same as Node.js)."""
    if not data:
        return ""
    import urllib.parse
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={urllib.parse.quote(data)}"


def generate_delivery_ticket_html(
    thread_id: int,
    customer_name: str,
    order_text: str,
    printed_by: str = "",
    nop_tien_topic_url: str = "",
) -> str:
    """Generate delivery ticket HTML.
    
    Matches Node.js DonHang.generateDeliveryTicketHTML() format.
    
    Args:
        thread_id: Order thread ID
        customer_name: Customer name
        order_text: Order text/description
        printed_by: Name of person who printed
        nop_tien_topic_url: URL for nộp tiền task topic (optional)
    
    Returns:
        HTML string for delivery ticket
    """
    # Build order topic URL (same as Node.js)
    internal_order_group_id = _get_internal_group_id(ORDER_GROUP_ID)
    order_topic_url = f"tg://privatepost?channel={internal_order_group_id}&post={thread_id}" if thread_id else ""
    
    # Generate QR codes
    qr_size = 64
    order_qr = _generate_qr_url(order_topic_url, qr_size) if order_topic_url else ""
    nop_qr = _generate_qr_url(nop_tien_topic_url, qr_size) if nop_tien_topic_url else ""
    
    # Format current time in Vietnamese timezone
    vn_now = datetime.now(timezone(timedelta(hours=7)))
    time_label = vn_now.strftime("%H:%M:%S %d/%m/%Y")
    
    # Escape values
    safe_name = _escape_html(customer_name or "Khách hàng")
    safe_text = _escape_html(order_text or "")
    safe_printed_by = _escape_html(printed_by or "—")
    
    # Build QR sections
    order_qr_html = ""
    if order_qr:
        order_qr_html = f'''<div><div class="meta" style="text-align:right">QR: Topic Đơn hàng</div><img src="{order_qr}" width="{qr_size}" height="{qr_size}"/></div>'''
    
    nop_qr_html = ""
    if nop_qr:
        nop_qr_html = f'''<div><div class="meta" style="text-align:right">QR: Topic Nộp tiền</div><img src="{nop_qr}" width="{qr_size}" height="{qr_size}"/></div>'''
    
    # Build HTML (matches Node.js format exactly)
    html = f'''<!DOCTYPE html><html lang="vi"><head>
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
    
    return html


async def _enqueue_html_for_print(html: str, copies: int = 1) -> None:
    """Queue HTML for physical printer via Firebase.
    
    Mirrors Node.js enqueueHtmlForPrint():
    - Writes HTML to meta/to_print N times (one per copy)
    - Adds print marker for tracking
    - Settle delay then delete between copies
    """
    ref = fb_ref(META_TO_PRINT_PATH)
    if ref is None:
        log.warning("Firebase not configured — skipping print queue")
        return
    
    try:
        import time
        import asyncio
        import re
        import random
        
        copies = max(1, copies)
        settle_ms = 0.12  # 120ms same as Node.js
        gap_ms = 0.22  # 220ms gap between copies (same as Node.js)
        batch_id = f"{int(time.time()*1000)}-{random.randint(100000, 999999)}"
        
        for i in range(copies):
            # Add print marker (same as Node.js)
            marker = f"print-queue:{batch_id}:copy:{i+1}/{copies}"
            marker_tag = f"<!-- {marker} -->"
            
            # Inject marker before </body> or append
            html_lower = html.lower()
            if "</body>" in html_lower:
                # Find the position of </body> (case-insensitive)
                match = re.search(r'</body>', html, re.IGNORECASE)
                if match:
                    pos = match.start()
                    html_with_marker = html[:pos] + marker_tag + "\n" + html[pos:]
                else:
                    html_with_marker = html + "\n" + marker_tag
            else:
                html_with_marker = html + "\n" + marker_tag
            
            # Write to Firebase
            ref.set(html_with_marker)
            
            # Settle delay
            if settle_ms > 0:
                await asyncio.sleep(settle_ms)
            
            # Delete after settle
            ref.delete()
            
            # Gap between copies (except after last copy)
            if i < copies - 1 and gap_ms > 0:
                await asyncio.sleep(gap_ms)
        
        log.info("Queued %d copy(ies) for printing", copies)
    except Exception as e:
        log.warning("Failed to queue for printing: %s", e)


async def print_delivery_ticket(
    client,
    thread_id: int,
    customer_name: str,
    order_text: str,
    printed_by: str = "",
    nop_tien_topic_url: str = "",
) -> None:
    """Generate and print delivery ticket.
    
    Mirrors Node.js DonHang.printDeliveryTicket():
    1. Generate HTML
    2. Queue for physical printer
    """
    html = generate_delivery_ticket_html(
        thread_id=thread_id,
        customer_name=customer_name,
        order_text=order_text,
        printed_by=printed_by,
        nop_tien_topic_url=nop_tien_topic_url,
    )
    
    # Queue for physical printer
    try:
        await _enqueue_html_for_print(html, copies=1)
    except Exception as e:
        log.warning("Failed to print delivery ticket: %s", e)
