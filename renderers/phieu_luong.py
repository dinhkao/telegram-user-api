"""HTML PHIẾU LƯƠNG TUẦN cho 1 thợ — in giấy, bắt chước layout hoá đơn (280px).

Thuần: nhận dữ liệu đã tính (days=[{ymd, money}], total) và trả chuỗi HTML. Nối:
renderers.common. Route dùng: server_app/production_dashboard_routes
(production_worker_payslip_handler) — số tiền tính từ production_store.report_slips
.compute_range_report (cùng nguồn với phiếu báo cáo lương văn phòng).
"""
from __future__ import annotations

from renderers.common import esc


def _money(n) -> str:
    return f"{int(round(n or 0)):,}".replace(",", ".") + "đ"


def _dmy(ymd: str) -> str:
    if not ymd or "-" not in str(ymd):
        return str(ymd or "?")
    y, m, d = str(ymd).split("-")
    return f"{d}/{m}/{y}"


def generate_payslip_html(worker_name: str, from_ymd: str, to_ymd: str,
                          days: list[dict], total) -> str:
    """days = [{ymd, money}] (đã sắp ngày tăng dần); total = tổng tiền cả kỳ."""
    if days:
        day_rows = "".join(
            f'<tr><td>{esc(_dmy(d.get("ymd")))}</td>'
            f'<td class="thanh-tien">{_money(d.get("money"))}</td></tr>'
            for d in days
        )
    else:
        day_rows = '<tr><td colspan="2" class="align-middle">Không có dữ liệu kỳ này</td></tr>'
    period = f"{_dmy(from_ymd)} → {_dmy(to_ymd)}" if (from_ymd or to_ymd) else ""
    html = (
        '<!DOCTYPE html><html lang="vi"><head>\n'
        '<meta charset="UTF-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'<title>Phiếu lương — {esc(worker_name)}</title>\n'
        '<style>\n'
        '  body { width: 280px; font-family: Arial, sans-serif; }\n'
        '  .title { text-align: center; font-weight: bold; font-size: 17px; }\n'
        '  .align-middle { text-align: center; vertical-align: middle; }\n'
        '  .thanh-tien { text-align: right; }\n'
        '  .ten-tho { font-size: 16px; font-weight: bold; }\n'
        '  table { width: 100%; border-collapse: collapse; }\n'
        '  td, th { padding: 3px; font-size: 14px; vertical-align: middle; }\n'
        '  th.hd { text-align: center; font-weight: bold; }\n'
        '  .hr-container { text-align: left; }\n'
        '  hr { margin: 5px auto; }\n'
        '  .tong td { font-size: 16px; font-weight: bold; border-top: 2px solid #000; }\n'
        '</style>\n'
        '</head><body>\n'
        '  <div class="title">PHIẾU LƯƠNG TUẦN</div>\n'
        f'  <div class="align-middle">{esc(period)}</div>\n'
        '  <div class="hr-container"><hr></div>\n'
        '  <table border="0">\n'
        '    <tr><td>CÔNG TY LÊ TRANG PHÁT</td></tr>\n'
        '    <tr><td>SĐT: 0941 586 542 | 0908 141 393</td></tr>\n'
        '  </table>\n'
        '  <div class="hr-container"><hr></div>\n'
        '  <table border="0">\n'
        f'    <tr><td class="ten-tho">Nhân viên: {esc(worker_name)}</td></tr>\n'
        '  </table>\n'
        '  <table border="1">\n'
        '    <tr><th class="hd">Ngày</th><th class="hd">Thành tiền</th></tr>\n'
        f'    {day_rows}\n'
        '  </table>\n'
        '  <table border="0">\n'
        f'    <tr class="tong"><td>TỔNG CỘNG</td><td class="thanh-tien">{_money(total)}</td></tr>\n'
        '  </table>\n'
        '</body></html>'
    )
    return html
