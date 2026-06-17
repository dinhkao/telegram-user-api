"""picking_sheet.py — Generate picking sheet HTML (Phiếu soạn hàng).

Mirrors Node.js generatePickingSheet() in groupDonHang.js.
Generates HTML with QR code for order link, product table from invoice.
Auto-triggered when a new order is created (via channel_handler.py).
"""
from __future__ import annotations
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta

from order_db import get_order_by_thread_id

log = logging.getLogger("picking_sheet")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
CHANNEL_DON_HANG_MOI = int(os.getenv("CHANNEL_DON_HANG_MOI", "-1002138495144"))
PICKING_PRINT_PATH = "meta/to_print2"  # Separate queue from delivery ticket (meta/to_print)


def _escape_html(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _get_internal_group_id(group_id: int) -> str:
    group_id_str = str(group_id)
    if group_id_str.startswith("-100"):
        return group_id_str[4:]
    return str(abs(group_id))


def _generate_qr_url(data: str, size: int = 120) -> str:
    if not data:
        return ""
    import urllib.parse
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={urllib.parse.quote(data)}"


def generate_picking_sheet_html(
    thread_id: int,
    order_text: str,
    invoice: list[dict] | None = None,
    channel_id: int | None = None,
    message_id: int | None = None,
    add_fix_banner: bool = False,
    manual_print_note: str | None = None,
) -> str:
    """Generate picking sheet HTML (Phiếu soạn hàng).

    Matches Node.js generatePickingSheet() format.

    Args:
        thread_id: Order thread ID
        order_text: Order text/description
        invoice: List of invoice items [{sp, sl, price, ...}]
        channel_id: Channel ID for QR code link (prefer main channel message)
        message_id: Message ID for QR code link
        add_fix_banner: Show "Đơn hàng được sửa đổi" banner
        manual_print_note: Optional manual print note

    Returns:
        HTML string for picking sheet
    """
    # Build QR link — prefer main channel message, fall back to topic
    internal_order_group_id = _get_internal_group_id(ORDER_GROUP_ID)
    order_topic_url = f"tg://privatepost?channel={internal_order_group_id}&post={thread_id}"

    qr_target = order_topic_url
    if channel_id and message_id:
        internal_channel_id = _get_internal_group_id(channel_id)
        qr_target = f"tg://privatepost?channel={internal_channel_id}&post={message_id}"

    qr_size = 120
    qr_url = _generate_qr_url(qr_target, qr_size)

    # Build product rows from invoice
    items = invoice or []
    product_rows = ""
    for idx, it in enumerate(items):
        name = _escape_html(it.get("sp", it.get("name", it.get("productName", "Sản phẩm"))))
        qty = it.get("sl", it.get("quantity", 0))
        product_rows += f"""<tr>
              <td class="stt">{idx + 1}</td>
              <td class="product-name">{name}</td>
              <td class="so-luong">{qty}</td>
            </tr>"""

    # Vietnam timezone
    vn_now = datetime.now(timezone(timedelta(hours=7)))
    now_str = vn_now.strftime("%H:%M:%S %d/%m/%Y")

    # Banners / notes
    fix_banner = '<div class="banner">Đơn hàng được sửa đổi. Hủy phiếu soạn hàng cũ</div>' if add_fix_banner else ""
    manual_note = f'<div class="manual-note">{_escape_html(manual_print_note)}</div>' if manual_print_note else ""

    safe_text = _escape_html(order_text or "")
    safe_id = _escape_html(str(thread_id))

    html = f"""<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>PHIẾU SOẠN HÀNG</title>
<style>
  body {{ width: 280px; font-family: Arial, sans-serif; }}
  .stt {{ width: 20px; text-align: center; }}
  .invoice-hd {{ text-align: center; font-weight: bold; }}
  .so-luong {{ text-align: center; font-size: 18px; }}
  .product-name {{ font-size: 18px; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td, th {{ padding: 2px; font-size: 14px; vertical-align: middle; }}
  .hr {{ margin: 5px auto; border: 0; border-top: 1px solid #000; }}
  .title {{ text-align:center; font-weight:bold; }}
  .order-text {{ white-space: pre-wrap; font-size: 20px; }}
  .order-id {{ font-weight: bold; font-size: 16px; }}
  .header {{ width:100%; }}
  .right {{ text-align:right; }}
  .align-top {{ vertical-align: top; }}
  .qrbox {{ text-align:right; vertical-align:top; }}
  .muted {{ color:#333; }}
  .banner {{ margin-bottom: 6px; font-weight: bold; color: #c00; }}
  .strike {{ text-decoration: line-through; }}
  .manual-note {{ margin-bottom: 6px; font-weight: bold; }}
</style>
</head><body>
  {manual_note}
  {fix_banner}
  <table class="header" border="0">
    <tr>
      <td class="align-top">
        <div class="title">PHIẾU SOẠN HÀNG</div>
        <div>{now_str}</div>
      </td>
      <td class="qrbox">
        <img src="{qr_url}" alt="QR tới đơn hàng" width="{qr_size}" height="{qr_size}" />
      </td>
    </tr>
  </table>
  <hr class="hr" />
  <div class="order-id">Mã đơn: {safe_id}</div>
  <div class="muted">Đơn: </div>
  <div class="order-text">{safe_text}</div>
  <hr class="hr" />
  <table border="1">
    <tr>
      <th class="stt"></th>
      <th class="invoice-hd">Sản phẩm</th>
      <th class="invoice-hd">SL</th>
    </tr>
    {product_rows}
  </table>
</body></html>"""

    return html


async def _enqueue_picking_html_for_print(html: str, copies: int = 1) -> bool:
    """Queue picking sheet HTML for physical printer via Firebase meta/to_print2.

    Same logic as delivery_ticket._enqueue_html_for_print but uses PICKING_PRINT_PATH.
    """
    from firebase_sync import _ref as fb_ref

    ref = fb_ref(PICKING_PRINT_PATH)
    if ref is None:
        log.warning("Firebase not configured — skipping picking sheet print queue")
        return False

    try:
        import asyncio
        import re
        import random
        import time

        copies = max(1, copies)
        settle_ms = 0.12
        gap_ms = 0.22
        batch_id = f"{int(time.time()*1000)}-{random.randint(100000, 999999)}"

        for i in range(copies):
            marker = f"print-queue:{batch_id}:copy:{i+1}/{copies}"
            marker_tag = f"<!-- {marker} -->"

            html_lower = html.lower()
            if "</body>" in html_lower:
                match = re.search(r'</body>', html, re.IGNORECASE)
                if match:
                    pos = match.start()
                    html_with_marker = html[:pos] + marker_tag + "\n" + html[pos:]
                else:
                    html_with_marker = html + "\n" + marker_tag
            else:
                html_with_marker = html + "\n" + marker_tag

            ref.set(html_with_marker)
            if settle_ms > 0:
                await asyncio.sleep(settle_ms)
            ref.delete()
            if i < copies - 1 and gap_ms > 0:
                await asyncio.sleep(gap_ms)

        log.info("Queued %d picking sheet copy(ies) for printing", copies)
        return True
    except Exception as e:
        log.warning("Failed to queue picking sheet for printing: %s", e)
        return False


async def generate_picking_sheet(client, conn, thread_id: int) -> bool:
    """Generate picking sheet, queue for printing, and send HTML file to order topic.

    Called automatically when new order is created (via channel_handler._auto_parse)
    or manually via 'in soan' command.

    Args:
        client: Telethon client (user account)
        conn: SQLite connection
        thread_id: Order thread ID

    Returns:
        True on success, False on failure
    """
    try:
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            log.warning("picking_sheet: order not found thread=%d", thread_id)
            return False

        order_text = order.get("text", "")
        invoice = order.get("invoice") or []
        channel_id = order.get("channel_id")
        message_id = order.get("message_id")

        # Generate HTML
        html = generate_picking_sheet_html(
            thread_id=thread_id,
            order_text=order_text,
            invoice=invoice,
            channel_id=channel_id,
            message_id=message_id,
        )

        # Queue for physical printer (non-blocking, don't fail on printer errors)
        try:
            await _enqueue_picking_html_for_print(html)
            # Notify in order topic
            await client.send_message(
                ORDER_GROUP_ID,
                "🖨️ Đã gửi lệnh in phiếu soạn hàng",
                reply_to=thread_id,
                link_preview=False,
            )
        except Exception as e:
            log.warning("Print queue / notification failed for thread=%d: %s", thread_id, e)

        # Send HTML file to order topic
        try:
            file_path = os.path.join(tempfile.gettempdir(), f"phieu_soan_{thread_id}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            await client.send_file(
                ORDER_GROUP_ID,
                file_path,
                reply_to=thread_id,
                force_document=True,
            )
            try:
                os.unlink(file_path)
            except Exception:
                pass
        except Exception as e:
            log.warning("Failed to send picking sheet file for thread=%d: %s", thread_id, e)

        log.info("Generated picking sheet for thread=%d", thread_id)
        return True
    except Exception as e:
        log.error("Error generating picking sheet for thread=%d: %s", thread_id, e)
        try:
            await client.send_message(
                ORDER_GROUP_ID,
                "❌ Lỗi khi tạo phiếu soạn hàng",
                reply_to=thread_id,
            )
        except Exception:
            pass
        return False
