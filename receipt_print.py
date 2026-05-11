"""receipt_print.py — Generate & send payment receipt HTML.

Mirrors Node.js generatePaymentReceiptPrint() + enqueueHtmlForPrint().
Two outputs:
  1. Firebase meta/to_print → physical printer (via RTDB watch)
  2. Telegram document → group chat
"""
from __future__ import annotations
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta

from firebase_sync import _ref as fb_ref

log = logging.getLogger("receipt_print")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
PRINT_PATH = os.getenv("FIREBASE_PRINT_PATH", "meta/to_print")
PRINT_SETTLE_MS = int(os.getenv("PRINT_SETTLE_MS", "120"))
PRINT_GAP_MS = int(os.getenv("PRINT_GAP_MS", "220"))


def _escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _format_money(val) -> str:
    """Format number as Vietnamese đồng."""
    try:
        num = int(val)
        return f"{num:,}đ"
    except (ValueError, TypeError):
        return "N/A"


def generate_receipt_html(
    customer_name: str,
    thread_id: int,
    old_debt: int | None,
    payment_amount: int,
    new_debt: int | None,
) -> tuple[str, str]:
    """Generate a payment receipt HTML file content.
    
    Returns (html_content, file_stamp).
    """
    vn_now = datetime.now(timezone(timedelta(hours=7)))
    time_label = vn_now.strftime("%H:%M:%S %d/%m/%Y")
    file_stamp = vn_now.strftime("%Y%m%d_%H%M%S")

    safe_name = _escape_html(customer_name or "Khách hàng")

    html = f"""<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Phiếu thu</title>
<style>
  body{{width:280px;font-family:Arial,sans-serif;margin:12px;font-size:16px;}}
  h1{{font-size:20px;margin:0 0 8px 0;}}
  .meta{{color:#555;margin-bottom:10px;}}
  table{{width:100%;border-collapse:collapse;}}
  td{{padding:6px 0;}}
  td.label{{color:#333;width:55%;}}
  td.value{{font-weight:600;text-align:right;}}
</style>
</head><body>
<h1>Phiếu thu</h1>
<div class="meta">Thời gian: {time_label}</div>
<div>Đơn hàng: <strong>#{thread_id}</strong></div>
<div>Khách hàng: <strong>{safe_name}</strong></div>
<table>
  <tr><td class="label">Nợ trước khi thu</td><td class="value">{_format_money(old_debt)}</td></tr>
  <tr><td class="label">Số tiền thanh toán</td><td class="value">{_format_money(payment_amount)}</td></tr>
  <tr><td class="label">Nợ sau khi thu</td><td class="value">{_format_money(new_debt)}</td></tr>
</table>
</body></html>"""

    return html, file_stamp


async def _enqueue_html_for_print(html: str, copies: int = 1) -> None:
    """Write HTML to Firebase meta/to_print for physical printer.
    
    Mirrors Node.js enqueueHtmlForPrint() — write → settle → delete.
    The printer process watches this path on Firebase RTDB.
    Adds an HTML comment marker for tracking: <!-- print-queue:batchId:copy:N/total -->
    """
    ref = fb_ref(PRINT_PATH)
    if ref is None:
        log.warning("Firebase not configured — skipping print queue")
        return

    batch_id = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}-{os.urandom(4).hex()}"

    for i in range(copies):
        marker = f"print-queue:{batch_id}:copy:{i + 1}/{copies}"
        payload = html.replace("</body>", f"<!-- {marker} -->\n</body>") if "</body>" in html else f"{html}\n<!-- {marker} -->"

        try:
            ref.set(payload)
            await asyncio.sleep(PRINT_SETTLE_MS / 1000.0)
            ref.delete()
        except Exception as e:
            log.warning("Print queue write/delete failed (copy %d/%d): %s", i + 1, copies, e)

        if i < copies - 1:
            await asyncio.sleep(PRINT_GAP_MS / 1000.0)

    log.info("Print queued to %s: copies=%d batch=%s", PRINT_PATH, copies, batch_id)


async def send_payment_receipt(
    client,
    thread_id: int,
    customer_name: str,
    payment_amount: int,
    old_debt: int | None = None,
    new_debt: int | None = None,
) -> None:
    """Generate receipt HTML, send to printer + Telegram group.
    
    Mirrors Node.js generatePaymentReceiptPrint():
    1. Generate HTML receipt
    2. Enqueue to Firebase meta/to_print → physical printer
    3. Save to temp file → send as document via Telegram
    """
    html, file_stamp = generate_receipt_html(
        customer_name=customer_name,
        thread_id=thread_id,
        old_debt=old_debt,
        payment_amount=payment_amount,
        new_debt=new_debt,
    )

    # 1. Queue to physical printer via Firebase
    try:
        await _enqueue_html_for_print(html, copies=1)
    except Exception as e:
        log.warning("Failed to enqueue print: %s", e)

    # 2. Send as Telegram document
    try:
        file_name = f"phieu_thu_{file_stamp}.html"
        file_path = os.path.join(tempfile.gettempdir(), file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        await client.send_file(
            ORDER_GROUP_ID,
            file_path,
            caption=f"📄 Phiếu thu — {customer_name} — {_format_money(payment_amount)}",
            reply_to=thread_id,
            force_document=True,
        )

        try:
            os.remove(file_path)
        except OSError:
            pass
    except Exception as e:
        log.warning("Failed to send receipt document: %s", e)

    log.info("Payment receipt processed: thread=%d customer=%s amount=%s",
             thread_id, customer_name, payment_amount)
