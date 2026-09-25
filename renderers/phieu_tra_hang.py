"""HTML HOÁ ĐƠN TRẢ HÀNG (phiếu trả, return_store) — cùng khổ/kiểu chữ với hoá đơn bán
KiotViet (renderers/inhoadon.py, body 280px) để ảnh gửi khách nhìn như một bộ.

THUẦN: nhận dict phiếu (items đã resolve tên hiện hành) + tên khách → chuỗi HTML, không
đọc DB/KiotViet (dữ liệu phiếu trả nằm hết ở app — HĐ KV giá âm chỉ là bản sao). Nối:
renderers.common (esc), renderers.invoice_parts (format_currency), utils.qty.
Dùng bởi server_app/return_image.py (HTML → PNG → ảnh của phiếu). Tests:
tests/test_return_image.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from renderers.common import esc
from renderers.invoice_parts import format_currency
from utils.qty import fmt_qty, line_total, parse_qty

_VN = timezone(timedelta(hours=7))


def _date_str(created_at) -> str:
    """created_at ISO (+07:00, hoặc UTC trần của SQLite) → 'HH:MM dd/mm/YYYY' giờ VN."""
    s = str(created_at or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return ""
    if dt.tzinfo is None:           # datetime('now') của SQLite = UTC trần
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_VN).strftime("%H:%M %d/%m/%Y")


def return_summary(slip: dict) -> list[tuple[str, str]]:
    """Các dòng tổng (nhãn, số đã định dạng). Phiếu ĐÃ có HĐ KiotViet + biết nợ trước →
    thêm Nợ trước / Trừ hàng trả / Còn nợ. Còn nợ = nợ trước − tổng trả (đúng số HĐ âm
    trừ), KHÔNG dùng debt_after vì resync nền có thể đã gộp biến động khác của khách."""
    total = float(slip.get("total") or 0)
    rows = [("Tổng tiền hàng trả", "-" + format_currency(round(total)))]   # phiếu TRẢ → số âm
    before = slip.get("debt_before")
    if slip.get("kv_invoice_id") and before is not None:
        before = float(before)
        after = before - total
        rows += [
            ("Nợ trước", ("-" if before < 0 else "") + format_currency(round(abs(before)))),
            ("Trừ hàng trả", "-" + format_currency(round(total))),
            ("Còn nợ", ("-" if after < 0 else "") + format_currency(round(abs(after)))),
        ]
    return rows


def generate_return_html(slip: dict, customer_name: str = "") -> str:
    """slip = dict phiếu trả (items [{sp, name?, sl, price}]) → HTML hoá đơn trả hàng."""
    invoiced = bool(slip.get("kv_invoice_id"))
    code = (slip.get("kv_invoice_code") or "") if invoiced else f"Phiếu trả #{slip.get('id')} (nháp)"
    date_str = _date_str(slip.get("created_at"))
    name = (customer_name or "").strip() or "Khách hàng"

    rows = []
    for i, it in enumerate(slip.get("items") or [], 1):
        sl = parse_qty(it.get("sl"))
        price = it.get("price") or 0
        label = it.get("name") or it.get("sp") or "?"
        rows.append(
            f'<tr><td class="stt">{i}</td><td>{esc(label)}</td>'
            f'<td class="so-luong">{esc(fmt_qty(sl))}</td>'
            f'<td class="so-luong">{format_currency(round(float(price)))}</td>'
            f'<td class="thanh-tien">{format_currency(line_total(price, sl))}</td></tr>')
    summary = "".join(
        f'<tr><td class="strict-width"></td><td class="to-bold">{esc(lbl)}</td>'
        f'<td class="money-column">{val}</td></tr>' for lbl, val in return_summary(slip))
    note = (slip.get("note") or "").strip()
    note_html = f'<div class="note">Ghi chú: {esc(note)}</div>' if note else ""

    return f"""<!DOCTYPE html><html lang="vi"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Hóa đơn trả hàng {esc(code)}</title>
<style>
  body {{ width: 280px; font-family: Arial, sans-serif; }}
  .stt {{ width: 20px; text-align: center; }}
  .invoice-hd {{ text-align: center; font-weight: bold; }}
  .so-luong {{ text-align: center; }}
  .thanh-tien {{ text-align: right; }}
  .strict-width {{ width: 40px; }}
  .to-bold {{ font-weight: bold; }}
  .money-column {{ font-size: 16px; text-align: right; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td, th {{ padding: 2px; font-size: 14px; vertical-align: middle; }}
  hr {{ margin: 5px auto; }}
  .kh-sdt {{ font-size: 16px; font-weight: bold; }}
  .center {{ text-align: center; }}
  .note {{ font-size: 13px; margin-top: 6px; }}
</style>
</head><body>
  <div class="center to-bold">HÓA ĐƠN TRẢ HÀNG</div>
  <div class="center">{esc(code)}</div>
  <div class="center">{esc(date_str)}</div>
  <hr>
  <table border="0">
    <tr><td>CÔNG TY LÊ TRANG PHÁT</td></tr>
    <tr><td>SĐT: 0941 586 542 | 0908 141 393</td></tr>
  </table>
  <hr>
  <table border="0"><tr><td class="kh-sdt">KH: {esc(name)}</td></tr></table>
  <table border="1">
    <tr><th class="stt"></th><th class="invoice-hd">Sản phẩm</th><th class="invoice-hd">SL</th>
      <th class="invoice-hd">Đơn giá</th><th class="invoice-hd">Thành tiền</th></tr>
    {"".join(rows)}
  </table>
  <br />
  <table border="0">{summary}</table>
  {note_html}
</body></html>"""
