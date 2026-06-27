from __future__ import annotations

from datetime import datetime, timezone, timedelta

from kiotviet import get_invoice_detail
from renderers.common import esc, qr_url, vn_now
from renderers.invoice_parts import build_product_rows, build_summary_rows, get_surcharges


def generate_invoice_html(invoice_or_id, debt: int = 0, hints: dict | None = None) -> str:
    hints = hints or {}
    if isinstance(invoice_or_id, int):
        invoice = get_invoice_detail(invoice_or_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_or_id} not found")
    elif isinstance(invoice_or_id, dict):
        invoice = invoice_or_id
    else:
        raise ValueError("Expected invoice ID (int) or invoice dict")
    details = invoice.get("invoiceDetails", [])
    product_rows, tong_tien_hang = build_product_rows(details)
    discount = invoice.get("discount", 0)
    surcharges = get_surcharges(invoice, hints)
    summary_rows, _, _, _ = build_summary_rows(tong_tien_hang, surcharges, discount, debt)
    purchase_date = invoice.get("purchaseDate") or vn_now().isoformat()
    try:
        dt = datetime.fromisoformat(str(purchase_date).replace("Z", "+00:00"))
        date_str = dt.strftime("%H:%M %d/%m/%Y")
    except Exception:
        date_str = vn_now().strftime("%H:%M %d/%m/%Y")
    customer_name = (hints.get("customerNameOverride") or "").strip() or invoice.get("customerName", "Khách hàng")
    order_topic_url = hints.get("orderTopicUrl", "")
    nop_tien_topic_url = hints.get("nopTienTopicUrl", "")
    disable_qr = bool(hints.get("disableQR"))
    qr_size = hints.get("qrSize", 60)
    qr_link = "" if disable_qr or not order_topic_url else qr_url(order_topic_url, qr_size, safe="")
    nop_qr_size = hints.get("nopTienQrSize", 54)
    nop_qr_link = "" if disable_qr or not nop_tien_topic_url else qr_url(nop_tien_topic_url, nop_qr_size, safe="")
    invoice_title = hints.get("invoiceTitle", "HÓA ĐƠN BÁN HÀNG")
    invoice_id_display = invoice.get("id", "")
    qr_cell = f'<td style="text-align:right; vertical-align:top;"><img src="{qr_link}" alt="QR tới topic đơn hàng" width="{qr_size}" height="{qr_size}" /></td>' if qr_link else "<td></td>"
    nop_cell = f'<div class="qr-bottom-right"><img src="{nop_qr_link}" alt="QR tới topic Nộp tiền" width="{nop_qr_size}" height="{nop_qr_size}" /></div>' if nop_qr_link else ""
    cell_font_size = "14px"
    money_font_size = "16px"
    customer_font_size = "16px"
    page_overrides = ""
    html = (
        f'<!DOCTYPE html><html lang="vi"><head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<title>Hóa đơn {invoice_id_display}</title>\n<style>\n  body {{ width: 280px; font-family: Arial, sans-serif; }}\n  {page_overrides}\n  .stt {{ width: 20px; text-align: center; }}\n  .invoice-hd {{ text-align: center; font-weight: bold; }}\n  .so-luong {{ text-align: center; }}\n  .don-vi {{ text-align: center; }}\n  .thanh-tien {{ text-align: right; }}\n  .strict-width {{ width: 40px; }}\n  .to-bold {{ font-weight: bold; }}\n  .money-column {{ font-size: {money_font_size}; text-align: right; font-weight: bold; }}\n  table {{ width: 100%; border-collapse: collapse; }}\n  td, th {{ padding: 2px; font-size: {cell_font_size}; vertical-align: middle; }}\n  .hr-container {{ text-align: left; }}\n  hr {{ margin: 5px auto; }}\n  .kh-sdt {{ font-size: {customer_font_size}; font-weight: bold; }}\n  .align-middle {{ text-align: center; vertical-align: middle; }}\n  .qr-bottom-right {{ text-align: right; margin-top: 6px; }}\n</style>\n</head><body>\n  <table border="0" style="width:100%">\n    <tr>\n      <td style="vertical-align:top;">\n        <div style="text-align:center; font-weight:bold;">{invoice_title}</div>\n        <div class="align-middle"></div>\n        <div class="align-middle">{invoice_id_display}</div>\n        <div class="align-middle">{date_str}</div>\n      </td>\n      {qr_cell}\n    </tr>\n  </table>\n  <div class="hr-container"><hr></div>\n  <table border="0">\n    <tr><td>CÔNG TY LÊ TRANG PHÁT</td></tr>\n    <tr><td>SĐT: 0941 586 542 | 0908 141 393</td></tr>\n  </table>\n  <div class="hr-container"><hr></div>\n  <table border="0">\n    <tr><td class="kh-sdt">KH: {esc(customer_name)}</td></tr>\n  </table>\n  <table border="1">\n    <tr>\n      <th class="stt"></th>\n      <th class="invoice-hd">Sản phẩm</th>\n      <th class="invoice-hd">SL</th>\n      <th class="invoice-hd">Đơn giá</th>\n      <th class="invoice-hd">Thành tiền</th>\n    </tr>\n    {product_rows}\n  </table>\n  <br />\n  <table border="0">\n    {summary_rows}\n  </table>\n  {nop_cell}\n</body></html>'
    )
    return html
