"""HTML PHIẾU LƯƠNG TUẦN — in giấy (khổ 280px kiểu hoá đơn). Hỗ trợ NHIỀU thợ trong
1 trang: mỗi thợ 1 phiếu, ngăn nhau bằng page-break để máy in TỰ CẮT giữa từng người.

Thuần: nhận dữ liệu đã tính (workers=[{name, days:[{ymd,money}], total}], khoảng ngày).
Nối: renderers.common. Route: server_app/production_dashboard_routes
(production_payslips_html_handler). Tiền từ production_store.report_slips.compute_range_report.
"""
from __future__ import annotations

from renderers.common import esc


def _money(n) -> str:
    return f"{int(round(n or 0)):,}".replace(",", ".")


def _dmy(ymd: str) -> str:
    if not ymd or "-" not in str(ymd):
        return str(ymd or "?")
    y, m, d = str(ymd).split("-")
    return f"{d}/{m}/{y}"


def _section(name: str, period: str, days: list[dict], total) -> str:
    if days:
        rows = "".join(
            f'<tr><td>{esc(_dmy(d.get("ymd")))}</td>'
            f'<td class="money">{_money(d.get("money"))}</td></tr>'
            for d in days
        )
    else:
        rows = '<tr><td colspan="2" class="mid">Không có dữ liệu kỳ này</td></tr>'
    return (
        '<div class="payslip">\n'
        '  <div class="title">PHIẾU LƯƠNG TUẦN</div>\n'
        f'  <div class="mid period">{esc(period)}</div>\n'
        f'  <div class="ten-tho">Nhân viên: {esc(name)}</div>\n'
        '  <table border="1">\n'
        '    <tr><th>Ngày</th><th>Thành tiền</th></tr>\n'
        f'    {rows}\n'
        f'    <tr class="tong"><td>TỔNG CỘNG</td><td class="money">{_money(total)}</td></tr>\n'
        '  </table>\n'
        '  <div class="cut">- - - - - - - - - - - - - - - -</div>\n'
        '</div>'
    )


def generate_payslips_html(from_ymd: str, to_ymd: str, workers: list[dict]) -> str:
    """workers = [{name, days:[{ymd, money}], total}] — mỗi phần tử 1 phiếu lương."""
    period = f"{_dmy(from_ymd)} → {_dmy(to_ymd)}" if (from_ymd or to_ymd) else ""
    if workers:
        body = "\n".join(_section(w.get("name") or "?", period, w.get("days") or [], w.get("total"))
                         for w in workers)
    else:
        body = '<div class="payslip mid">Chưa chọn nhân viên</div>'
    return (
        '<!DOCTYPE html><html lang="vi"><head>\n'
        '<meta charset="UTF-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        '<title>Phiếu lương</title>\n'
        '<style>\n'
        # @page size:auto = MỖI phiếu 1 trang giấy ngắn (không phải A4) → máy in nhiệt
        # cắt ĐÚNG sau từng phiếu; margin:0 bỏ header/footer trình duyệt. (Máy in phải
        # bật "cut per page"/tự cắt trong driver thì mới cắt giấy vật lý.)
        '  @page { size: 76mm auto; margin: 0; }\n'
        '  html, body { margin: 0; padding: 0; }\n'
        '  body { width: 76mm; font-family: Arial, sans-serif; }\n'
        '  .payslip { break-after: page; page-break-after: always; '
        'break-inside: avoid; page-break-inside: avoid; padding: 3mm 2mm 5mm; '
        'box-sizing: border-box; }\n'
        '  .payslip:last-child { break-after: auto; page-break-after: auto; }\n'
        '  .title { text-align: center; font-weight: bold; font-size: 18px; margin-top: 6px; }\n'
        '  .mid { text-align: center; }\n'
        '  .period { font-size: 13px; margin-bottom: 4px; }\n'
        '  .ten-tho { font-size: 17px; font-weight: bold; margin: 4px 0; }\n'
        '  table { width: 100%; border-collapse: collapse; }\n'
        '  th, td { padding: 3px 4px; font-size: 15px; vertical-align: middle; }\n'
        '  th { font-weight: bold; }\n'
        '  .money { text-align: right; font-size: 20px; font-weight: bold; '
        'font-variant-numeric: tabular-nums; }\n'
        '  .tong td { font-size: 22px; font-weight: bold; border-top: 2px solid #000; }\n'
        '  .cut { text-align: center; letter-spacing: 2px; margin: 8px 0 2px; }\n'
        '  .payslip:last-child .cut { display: none; }\n'
        '</style>\n'
        '</head><body>\n'
        f'{body}\n'
        '</body></html>'
    )
