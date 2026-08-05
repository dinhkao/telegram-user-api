"""HTML PHIẾU LƯƠNG THÁNG 1 thợ — in giấy KHỔ HOÁ ĐƠN (body 280px như hoá đơn KiotViet
của đơn hàng, renderers/inhoadon.py), giấy dài tuỳ nội dung (@page size: 76mm auto).

3 khối, kẻ ô như bảng tính: (1) bảng TIỀN tháng → THỰC NHẬN · (2) CHẤM CÔNG từng ngày
(4 mốc giờ + giờ công + giờ TC) · (3) ỨNG LƯƠNG từng lần; cuối phiếu in TÊN thợ cỡ lớn
để phát phiếu khỏi lộn người.

Thuần: nhận payload đã dựng sẵn (salary_store.payslip.build_payslip) — không đọc DB,
không tính tiền. Route: server_app/payslip_routes.py. Nối: renderers.common.
"""
from __future__ import annotations

from renderers.common import esc


def _money(n) -> str:
    v = int(round(n or 0))
    s = f"{abs(v):,}".replace(",", ".")
    return f"-{s}" if v < 0 else s


def _num(n) -> str:
    """Số lẻ kiểu Việt: 23.6 → '23,6'; số tròn bỏ phần lẻ ('8,0' → '8')."""
    f = float(n or 0)
    return (f"{f:g}" if abs(f - round(f)) < 1e-9 else f"{f:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def _hrs(n) -> str:
    """GIỜ luôn 1 số lẻ ('8,0' · '0,0') — cột giờ/tăng ca thẳng hàng, đọc nhanh."""
    return f"{float(n or 0):.1f}".replace(".", ",")


def _line_row(ln: dict) -> str:
    cls = "tong" if ln.get("total") else ""
    if ln.get("kind") == "num":
        val = _hrs(ln["value"]) if ln.get("unit") == "h" else _num(ln.get("value"))
    else:
        val = _money(ln.get("value"))
        cls = (cls + " neg").strip() if float(ln.get("value") or 0) < 0 else cls
    return (f'<tr class="{cls}"><td>{esc(ln.get("label") or "")}</td>'
            f'<td class="money">{esc(val)}</td></tr>')


def _day_row(d: dict) -> str:
    slots = list(d.get("slots") or ["", "", "", ""])[:4]
    while len(slots) < 4:
        slots.append("")
    cells = "".join(f'<td class="gio">{esc(s) if s else ":"}</td>' for s in slots)
    dow = d.get("dow") or ""
    if d.get("sunday"):
        dow += "*"                     # chủ nhật = tăng ca toàn bộ (không có ngày công)
    day = d.get("d") or ""
    if d.get("more"):
        day += f'<sup>+{int(d["more"])}</sup>'   # còn mốc chấm không đủ ô để hiện
    return (f'<tr><td class="ngay">{day}</td><td class="thu">{esc(dow)}</td>{cells}'
            f'<td class="num">{esc(_hrs(d.get("gio")))}</td>'
            f'<td class="num">{esc(_hrs(d.get("tc")))}</td></tr>')


def _cham_cong(p: dict) -> str:
    days = p.get("days") or []
    if not days:
        return ""
    tot = p.get("day_total") or {}
    rows = "".join(_day_row(d) for d in days)
    return (
        '<div class="sec">CHẤM CÔNG</div>\n'
        '<table border="1" class="cc">\n'
        '  <tr><th>Ngày</th><th>Thứ</th><th colspan="2">Sáng</th><th colspan="2">Chiều</th>'
        '<th>Giờ</th><th>TC</th></tr>\n'
        f'{rows}\n'
        f'  <tr class="tong"><td colspan="6">TỔNG ({_num(tot.get("cong"))} công)</td>'
        f'<td class="num">{_hrs(tot.get("gio"))}</td>'
        f'<td class="num">{_hrs(tot.get("tc"))}</td></tr>\n'
        '</table>'
    )


def _ung_luong(p: dict) -> str:
    adv = p.get("advances") or []
    if not adv:
        return ""
    rows = "".join(
        f'<tr><td class="ngay">{esc(a.get("date") or "")}</td>'
        f'<td class="money">{esc(_money(a.get("amount")))}</td>'
        f'<td>{esc(a.get("note") or "")}</td></tr>' for a in adv
    )
    return (
        '<div class="sec">ỨNG LƯƠNG</div>\n'
        '<table border="1" class="ul">\n'
        f'{rows}\n'
        f'  <tr class="tong"><td>TỔNG</td><td class="money">{_money(p.get("adv_total"))}</td><td></td></tr>\n'
        '</table>'
    )


_CSS = """
  @page { size: 76mm auto; margin: 0; }
  html, body { margin: 0; padding: 0; }
  body { width: 280px; font-family: Arial, sans-serif; padding: 3mm 2mm 6mm; box-sizing: border-box; }
  .title { text-align: center; font-weight: bold; font-size: 19px; margin-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 2px; }
  td, th { padding: 2px 3px; font-size: 13px; vertical-align: middle; }
  th { font-weight: bold; text-align: center; }
  .money { text-align: right; font-weight: bold; white-space: nowrap;
           font-variant-numeric: tabular-nums; }
  .neg td { color: #000; }
  .tong td { font-weight: bold; border-top: 2px solid #000; }
  tr.tong td.money { font-size: 16px; }
  .ten td { font-size: 16px; font-weight: bold; }
  .sec { font-weight: bold; font-size: 14px; margin: 8px 0 3px; }
  .cut { text-align: center; letter-spacing: 2px; margin: 6px 0 2px; }
  .cc td, .cc th { font-size: 11px; padding: 1px 2px; }
  .cc .ngay, .cc .thu { white-space: nowrap; }
  .cc .gio, .cc .num { text-align: center; font-variant-numeric: tabular-nums; }
  .cc sup { font-size: 8px; }
  .ul td { font-size: 12px; }
  .ky { margin-top: 10px; text-align: center; font-size: 26px; font-weight: bold; }
"""


def generate_payslip_month_html(p: dict) -> str:
    """payload = salary_store.payslip.build_payslip(...)."""
    lines = "".join(_line_row(ln) for ln in (p.get("lines") or []))
    name = esc(p.get("name") or "?")
    return (
        '<!DOCTYPE html><html lang="vi"><head>\n'
        '<meta charset="UTF-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'<title>Phiếu lương {name} — {esc(p.get("ym_label") or "")}</title>\n'
        f'<style>{_CSS}</style>\n'
        '</head><body>\n'
        '  <div class="title">PHIẾU LƯƠNG THÁNG</div>\n'
        '  <table border="1">\n'
        f'    <tr><td>Kỳ lương</td><td class="money">{esc(p.get("ym_label") or "")}</td></tr>\n'
        f'    <tr><td>Ngày in phiếu</td><td class="money">{esc(p.get("printed") or "")}</td></tr>\n'
        f'    <tr class="ten"><td>Tên</td><td class="money">{name}</td></tr>\n'
        f'{lines}\n'
        '  </table>\n'
        f'{_cham_cong(p)}\n'
        f'{_ung_luong(p)}\n'
        f'  <div class="ky">{name}</div>\n'
        '  <div class="cut">- - - - - - - - - - - - - - - -</div>\n'
        '</body></html>'
    )
