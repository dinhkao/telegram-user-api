"""inhoadon.py — Generate invoice HTML identical to Node.js inhoadon.js.

Ports generateInvoiceHTML() exactly — same HTML structure, same QR codes,
same formatting. Uses KiotViet API to fetch real invoice details.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

from kiotviet import get_invoice_detail

log = logging.getLogger("inhoadon")


def _format_currency(amount) -> str:
    """Format number to Vietnamese locale string without currency symbol."""
    try:
        return f"{int(amount):,}"
    except (ValueError, TypeError):
        return str(amount)


def _parse_number(v):
    if isinstance(v, (int, float)):
        return int(v)
    if not v:
        return 0
    import re
    return int(re.sub(r"[^\d]", "", str(v))) or 0


def _get_surcharges(invoice: dict, hints: dict | None = None) -> list[dict]:
    """Extract surcharge items with labels (same logic as Node.js getSurcharges)."""
    hints = hints or {}
    surcharges = []

    surcharge_list = invoice.get("invoiceOrderSurcharges", [])
    if isinstance(surcharge_list, list):
        for s in surcharge_list:
            price = s.get("price") or s.get("amount") or 0
            if price > 0:
                raw_name = (s.get("name") or "").strip().lower()
                code = str(s.get("code") or "")
                code_lc = code.lower()
                s_id = s.get("id")

                is_shipping = s_id == 1000000298 or code == "THK000003"
                is_vat = s_id == 1865 or code == "THK000001"
                looks_like_vat = "vat" in code_lc or "tax" in code_lc or "vat" in raw_name
                looks_like_ship = any(k in code_lc for k in ["ship", "transport", "delivery"]) or "vận chuyển" in raw_name or "van chuyen" in raw_name

                generic_names = {"phí khác", "phi khac", "khác", "khac", "lệ phí khác", "le phi khac"}
                is_generic = raw_name in generic_names

                if is_shipping or looks_like_ship:
                    name = "Phí vận chuyển"
                elif is_vat or looks_like_vat:
                    name = "VAT"
                elif (s.get("name") or "").strip() and not is_generic:
                    name = s["name"].strip()
                elif code:
                    name = "Phí khác"
                else:
                    name = "Phí khác"

                surcharges.append({"name": name, "amount": price})

    # Post-process with hints
    try:
        expected_vat = int(hints.get("expectedVAT", 0))
        expected_pvc = int(hints.get("expectedPVC", 0))
        has_label = lambda l: any(s["name"] == l for s in surcharges)

        for s in surcharges:
            if s["name"] == "Phí khác":
                if not has_label("VAT") and expected_vat > 0 and abs(s["amount"] - expected_vat) < 1:
                    s["name"] = "VAT"
                elif not has_label("Phí vận chuyển") and expected_pvc > 0 and abs(s["amount"] - expected_pvc) < 1:
                    s["name"] = "Phí vận chuyển"
    except Exception:
        pass

    return surcharges


def generate_invoice_html(invoice_or_id, debt: int = 0, hints: dict | None = None) -> str:
    """Generate the EXACT same HTML as Node.js generateInvoiceHTML().
    
    Args:
        invoice_or_id: KiotViet invoice ID (int) OR pre-fetched invoice dict
        debt: Previous debt amount for display
        hints: Optional {expectedVAT, expectedPVC, customerNameOverride, showUnit,
                         orderTopicUrl, nopTienTopicUrl, disableQR, qrSize,
                         invoiceTitle, summaryMode}
    """
    hints = hints or {}

    if isinstance(invoice_or_id, int):
        invoice = get_invoice_detail(invoice_or_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_or_id} not found")
    elif isinstance(invoice_or_id, dict):
        invoice = invoice_or_id
    else:
        raise ValueError("Expected invoice ID (int) or invoice dict")

    show_unit = bool(hints.get("showUnit"))
    cell_font_size = "14px"
    money_font_size = "16px"
    customer_font_size = "16px"
    page_overrides = ""

    # Product rows
    details = invoice.get("invoiceDetails", [])
    product_rows = ""
    for i, item in enumerate(details):
        name = item.get("productName") or item.get("productCode", "?")
        qty = item.get("quantity", 0)
        price = item.get("price", 0)
        sub = item.get("subTotal") or (price * qty)
        product_rows += f"""<tr>
        <td class="stt">{i + 1}</td>
        <td>{name}</td>
        <td class="so-luong">{qty}</td>
        <td class="so-luong">{_format_currency(price)}</td>
        <td class="thanh-tien">{_format_currency(sub)}</td>
      </tr>"""

    tong_tien_hang = sum(
        d.get("subTotal") or (d.get("price", 0) * d.get("quantity", 0))
        for d in details
    )
    discount = invoice.get("discount", 0)
    surcharges = _get_surcharges(invoice, hints)
    total_surcharges = sum(s["amount"] for s in surcharges)
    tong_don_nay = tong_tien_hang + total_surcharges - discount
    tong_thanh_toan = tong_tien_hang + total_surcharges - discount + debt

    # Summary rows
    summary_rows = (
        f"""<tr><td class="strict-width"></td><td class="to-bold">Tổng tiền hàng</td><td class="money-column">{_format_currency(tong_tien_hang)}</td></tr>"""
        + "".join(
            f"""<tr><td></td><td class="to-bold">{s['name']}</td><td class="money-column">{_format_currency(s['amount'])}</td></tr>"""
            for s in surcharges
        )
        + (f"""<tr><td></td><td class="to-bold">Giảm giá</td><td class="money-column">-{_format_currency(discount)}</td></tr>""" if discount > 0 else "")
        + (f"""<tr><td></td><td class="to-bold">Tổng đơn này</td><td class="money-column">{_format_currency(tong_don_nay)}</td></tr>""" if (debt != 0 and (total_surcharges > 0 or discount > 0)) else "")
        + (f"""<tr><td></td><td class="to-bold">Nợ trước</td><td class="money-column">{'-' if debt < 0 else ''}{_format_currency(abs(debt))}</td></tr>""" if debt != 0 else "")
        + f"""<tr><td></td><td class="to-bold">Tổng thanh toán</td><td class="money-column">{_format_currency(tong_thanh_toan)}</td></tr>"""
    )

    # Date
    purchase_date = invoice.get("purchaseDate") or datetime.now(timezone(timedelta(hours=7))).isoformat()
    try:
        dt = datetime.fromisoformat(str(purchase_date).replace("Z", "+00:00"))
        date_str = dt.strftime("%H:%M %d/%m/%Y")
    except Exception:
        date_str = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M %d/%m/%Y")

    customer_name = (hints.get("customerNameOverride") or "").strip() or invoice.get("customerName", "Khách hàng")
    order_topic_url = hints.get("orderTopicUrl", "")
    nop_tien_topic_url = hints.get("nopTienTopicUrl", "")
    disable_qr = bool(hints.get("disableQR"))

    qr_size = hints.get("qrSize", 60)
    qr_url = ""
    if not disable_qr and order_topic_url:
        from urllib.parse import quote
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size={qr_size}x{qr_size}&data={quote(order_topic_url, safe='')}"

    nop_qr_size = hints.get("nopTienQrSize", 54)
    nop_qr_url = ""
    if not disable_qr and nop_tien_topic_url:
        from urllib.parse import quote
        nop_qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size={nop_qr_size}x{nop_qr_size}&data={quote(nop_tien_topic_url, safe='')}"

    invoice_title = hints.get("invoiceTitle", "HÓA ĐƠN BÁN HÀNG")
    invoice_id_display = invoice.get("id", "")

    # ── EXACT HTML from Node.js inhoadon.js ──────────────────────
    html = f"""<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Hóa đơn {invoice_id_display}</title>
<style>
  body {{ width: 280px; font-family: Arial, sans-serif; }}
  {page_overrides}
  .stt {{ width: 20px; text-align: center; }}
  .invoice-hd {{ text-align: center; font-weight: bold; }}
  .so-luong {{ text-align: center; }}
  .don-vi {{ text-align: center; }}
  .thanh-tien {{ text-align: right; }}
  .strict-width {{ width: 40px; }}
  .to-bold {{ font-weight: bold; }}
  .money-column {{ font-size: {money_font_size}; text-align: right; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td, th {{ padding: 2px; font-size: {cell_font_size}; vertical-align: middle; }}
  .hr-container {{ text-align: left; }}
  hr {{ margin: 5px auto; }}
  .kh-sdt {{ font-size: {customer_font_size}; font-weight: bold; }}
  .align-middle {{ text-align: center; vertical-align: middle; }}
  .qr-bottom-right {{ text-align: right; margin-top: 6px; }}
</style>
</head><body>
  <table border="0" style="width:100%">
    <tr>
      <td style="vertical-align:top;">
        <div style="text-align:center; font-weight:bold;">{invoice_title}</div>
        <div class="align-middle"></div>
        <div class="align-middle">{invoice_id_display}</div>
        <div class="align-middle">{date_str}</div>
      </td>
      {f'<td style="text-align:right; vertical-align:top;"><img src="{qr_url}" alt="QR tới topic đơn hàng" width="{qr_size}" height="{qr_size}" /></td>' if qr_url else '<td></td>'}
    </tr>
  </table>
  <div class="hr-container"><hr></div>
  <table border="0">
    <tr><td>CÔNG TY LÊ TRANG PHÁT</td></tr>
    <tr><td>SĐT: 0941 586 542 | 0908 141 393</td></tr>
  </table>
  <div class="hr-container"><hr></div>
  <table border="0">
    <tr><td class="kh-sdt">KH: {customer_name}</td></tr>
  </table>
  <table border="1">
    <tr>
      <th class="stt"></th>
      <th class="invoice-hd">Sản phẩm</th>
      <th class="invoice-hd">SL</th>
      <th class="invoice-hd">Đơn giá</th>
      <th class="invoice-hd">Thành tiền</th>
    </tr>
    {product_rows}
  </table>
  <br />
  <table border="0">
    {summary_rows}
  </table>
  {f'<div class="qr-bottom-right"><img src="{nop_qr_url}" alt="QR tới topic Nộp tiền" width="{nop_qr_size}" height="{nop_qr_size}" /></div>' if nop_qr_url else ''}
</body></html>"""

    return html
