"""PHIẾU LƯƠNG THÁNG của 1 thợ — dựng NỘI DUNG phiếu, logic THUẦN (không IO).

Nhận dữ liệu đã đọc sẵn (1 dòng bảng lương tháng của compute_month_payroll + các khoản
phụ cấp + các lần ứng + giờ chấm công từng ngày) → trả payload 3 khối để in:
- `lines`  : bảng tiền (ngày công → từng khoản cộng/trừ → THỰC NHẬN). Số lấy NGUYÊN từ
             dòng bảng lương nên phiếu in luôn khớp `#/luong-thang`, không tính lại tiền.
- `days`   : chấm công từng ngày (4 mốc giờ + giờ công + giờ tăng ca), ĐỦ MỌI NGÀY của
             tháng (ngày nghỉ vẫn có dòng trống) — giờ công quy bằng
             attendance_store.domain.work_stats, cùng luật với bảng lương.
- `advances`: từng lần ứng lương.

Nối: attendance_store.domain (thuần). Vẽ HTML: renderers/phieu_luong_thang.py.
Đọc DB + route: server_app/payslip_routes.py. Tests: tests/test_payslip.py.
"""
from __future__ import annotations

import calendar
from datetime import date

from attendance_store.domain import work_stats

_DOW = ("T.2", "T.3", "T.4", "T.5", "T.6", "T.7", "CN")
_NOON = 12 * 60


def _dmy(ymd: str) -> str:
    """'2026-06-01' → '01/06/2026'; chuỗi hỏng trả nguyên."""
    if not ymd or str(ymd).count("-") != 2:
        return str(ymd or "")
    y, m, d = str(ymd).split("-")
    return f"{d}/{m}/{y}"


def _money_line(label: str, value, *, neg: bool = False, total: bool = False) -> dict:
    v = round(float(value or 0))
    return {"label": label, "value": -v if neg else v, "kind": "money", "total": total}


def _num_line(label: str, value, unit: str = "") -> dict:
    """unit='h' → renderer in 1 số lẻ cố định (giờ); "" → số tự nhiên (ngày công)."""
    return {"label": label, "value": float(value or 0), "kind": "num", "unit": unit}


def _slots(times: list[str]) -> tuple[list[str], int]:
    """['HH:MM' tăng dần] → 4 ô (vào/ra sáng, vào/ra chiều) + số mốc KHÔNG hiện được.

    Chia theo BUỔI (trước/sau 12h) chứ không ghép tuần tự, để ngày chỉ làm buổi chiều
    vẫn nằm đúng 2 ô sau — nhìn phiếu là biết nghỉ buổi nào. Buổi có >2 mốc thì lấy
    mốc đầu + mốc cuối (khoảng có mặt vẫn đúng) và đếm phần dôi ra vào `more`.
    """
    sub = [t for t in times if len(t) >= 5]
    morning = [t for t in sub if int(t[:2]) * 60 + int(t[3:5]) < _NOON]
    after = [t for t in sub if int(t[:2]) * 60 + int(t[3:5]) >= _NOON]
    out: list[str] = []
    more = 0
    for group in (morning, after):
        out.append(group[0] if group else "")
        out.append(group[-1] if len(group) > 1 else "")
        more += max(0, len(group) - 2)
    return out, more


def _days(ym: str, times_by_day: dict, today_ymd: str = "") -> tuple[list[dict], dict]:
    """Mọi ngày của tháng (tháng ĐANG CHẠY thì dừng ở hôm nay — khỏi in cả chục dòng
    trống của ngày chưa tới). Trả (danh sách ngày, tổng công/tăng ca)."""
    y, m = (int(x) for x in ym.split("-")[:2])
    last = calendar.monthrange(y, m)[1]
    if today_ymd[:7] == ym:
        try:
            last = min(last, int(today_ymd[8:10]))
        except ValueError:
            pass
    rows, tot_work, tot_ot = [], 0, 0
    for d in range(1, last + 1):
        ymd = f"{y:04d}-{m:02d}-{d:02d}"
        times = sorted(times_by_day.get(ymd) or [])
        work, ot = work_stats(times, ymd) if times else (0, 0)
        tot_work += work
        tot_ot += ot
        slots, more = _slots(times)
        rows.append({
            "ymd": ymd, "d": f"{d:02d}/{m:02d}",
            "dow": _DOW[date(y, m, d).weekday()],
            "sunday": date(y, m, d).weekday() == 6,
            "slots": slots, "more": more,
            "gio": round(work / 60.0, 1), "tc": round(ot / 60.0, 1),
        })
    return rows, {"cong": round(tot_work / 480.0, 2), "gio": round(tot_work / 60.0, 1),
                  "tc": round(tot_ot / 60.0, 1)}


def _wage_lines(r: dict) -> list[dict]:
    """Phần LƯƠNG GỐC của bảng tiền — khác nhau theo loại lương của thợ."""
    wt = (r.get("wage_type") or "product")
    lines: list[dict] = []
    if wt == "product":
        lines.append(_money_line("Lương sản phẩm", r.get("luong_sp")))
        if round(float(r.get("pc_phieu") or 0)):
            # đã NẰM TRONG lương sản phẩm — ghi để thợ đối chiếu, KHÔNG cộng lần nữa
            lines.append(_money_line("  (trong đó phụ cấp phiếu SX)", r.get("pc_phieu")))
        return lines
    lines.append(_money_line("Mốc lương tháng", r.get("monthly_salary")))
    lines.append(_money_line("Lương theo ngày công", r.get("luong_cong")))
    if wt != "time_flat":
        lines.append(_money_line("Lương tăng ca", r.get("luong_tc")))
    return lines


def build_payslip(r: dict, allowances: list[dict], advances: list[dict],
                  times_by_day: dict, *, ym: str, today_ymd: str = "") -> dict:
    """r = 1 dòng compute_month_payroll; allowances/advances = khoản CÒN HIỆU LỰC;
    times_by_day = {'YYYY-MM-DD': ['HH:MM', ...]} của đúng thợ này."""
    wt = (r.get("wage_type") or "product")
    lines: list[dict] = [
        _num_line("Số ngày công", r.get("cong")),
        _num_line("Số giờ tăng ca" + (" (đã gộp vào ngày công)" if wt == "time_flat" else ""),
                  r.get("ot_gio"), "h"),
    ]
    lines += _wage_lines(r)
    if r.get("cc_on"):
        lines.append(_money_line("Thưởng chuyên cần", r.get("thuong_cc")))
    if r.get("vs_on"):
        lines.append(_money_line("Thưởng vệ sinh", r.get("thuong_vs")))
    if round(float(r.get("thuong") or 0)):
        lines.append(_money_line("Thưởng khác", r.get("thuong")))
    for a in allowances:
        label = (a.get("note") or "").strip() or "khác"
        if a.get("calc_label"):
            label = f"{label} ({a['calc_label']})"
        lines.append(_money_line(f"Phụ cấp {label}", a.get("amount")))
    if round(float(r.get("ung_weekly") or 0)):
        lines.append(_money_line("Trừ lương tuần đã nhận", r.get("ung_weekly"), neg=True))
    if round(float(r.get("ung_manual") or 0)):
        lines.append(_money_line("Trừ tạm ứng", r.get("ung_manual"), neg=True))
    if round(float(r.get("bhxh") or 0)):
        lines.append(_money_line("Trừ BHXH", r.get("bhxh"), neg=True))
    lines.append(_money_line("THỰC NHẬN", r.get("thuc_lanh"), total=True))

    days, tot = _days(ym, times_by_day, today_ymd)
    adv = [{"date": _dmy(a.get("adv_date") or ""), "amount": round(float(a.get("amount") or 0)),
            "note": (a.get("note") or "").strip()} for a in advances]
    y, m = ym.split("-")[:2]
    return {
        "ym": ym, "ym_label": f"Tháng {m}/{y}",
        "name": r.get("name") or "?",
        "printed": _dmy(today_ymd),
        "lines": lines,
        "days": days, "day_total": tot,
        "advances": adv, "adv_total": sum(a["amount"] for a in adv),
    }
