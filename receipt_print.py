"""receipt_print.py — Generate & send payment receipt HTML as document.

Mirrors Node.js generatePaymentReceiptPrint() in groupDonHang.js.
Generates an HTML receipt file, saves to temp, sends as document to order group.
"""
from __future__ import annotations
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta

log = logging.getLogger("receipt_print")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


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
    # Vietnam time
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


async def send_payment_receipt(
    client,
    thread_id: int,
    customer_name: str,
    payment_amount: int,
    old_debt: int | None = None,
    new_debt: int | None = None,
) -> None:
    """Generate receipt HTML and send as document to the order group.
    
    Mirrors Node.js generatePaymentReceiptPrint():
    1. Generate HTML receipt
    2. Save to temp file
    3. Send as document via client.send_file()
    """
    try:
        html, file_stamp = generate_receipt_html(
            customer_name=customer_name,
            thread_id=thread_id,
            old_debt=old_debt,
            payment_amount=payment_amount,
            new_debt=new_debt,
        )

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

        log.info("Payment receipt sent: thread=%d customer=%s amount=%s",
                 thread_id, customer_name, payment_amount)
    except Exception as e:
        log.warning("Failed to send payment receipt: %s", e)
