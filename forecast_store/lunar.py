"""Âm lịch Việt Nam (múi giờ +7) — thuật toán Hồ Ngọc Đức, thuần, không phụ thuộc.
`solar2lunar(d, m, y)` → (ngày, tháng, năm, nhuận). `lunar_label` → "28/7 ÂL Bính Ngọ".
`find_solar(ld, lm, around)` → ngày dương gần `around` nhất có cùng ngày/tháng âm.
Dùng bởi forecast_store.engine. Test: tests/test_forecast_lunar.py.
"""
from __future__ import annotations

import datetime as dt
import math

_CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
_CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]


def _jd(dd: int, mm: int, yy: int) -> int:
    a = (14 - mm) // 12
    y = yy + 4800 - a
    m = mm + 12 * a - 3
    jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    if jd < 2299161:
        jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    return jd


def _new_moon(k: int) -> float:
    T = k / 1236.85
    T2, T3 = T * T, T * T * T
    dr = math.pi / 180
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3
    jd1 += 0.00033 * math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr)
    M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3
    Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3
    F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3
    C1 = (0.1734 - 0.000393 * T) * math.sin(M * dr) + 0.0021 * math.sin(2 * dr * M)
    C1 -= 0.4068 * math.sin(Mpr * dr) + 0.0161 * math.sin(dr * 2 * Mpr)
    C1 -= 0.0004 * math.sin(dr * 3 * Mpr)
    C1 += 0.0104 * math.sin(dr * 2 * F) - 0.0051 * math.sin(dr * (M + Mpr))
    C1 -= 0.0074 * math.sin(dr * (M - Mpr)) + 0.0004 * math.sin(dr * (2 * F + M))
    C1 -= 0.0004 * math.sin(dr * (2 * F - M)) - 0.0006 * math.sin(dr * (2 * F + Mpr))
    C1 += 0.0010 * math.sin(dr * (2 * F - Mpr)) + 0.0005 * math.sin(dr * (2 * Mpr + M))
    if T < -11:
        deltat = 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3
    else:
        deltat = -0.000278 + 0.000265 * T + 0.000262 * T2
    return jd1 + C1 - deltat


def _sun_long(jdn: float) -> float:
    T = (jdn - 2451545.0) / 36525
    T2 = T * T
    dr = math.pi / 180
    M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2
    L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2
    DL = (1.914600 - 0.004817 * T - 0.000014 * T2) * math.sin(dr * M)
    DL += (0.019993 - 0.000101 * T) * math.sin(dr * 2 * M) + 0.000290 * math.sin(dr * 3 * M)
    L = (L0 + DL) * dr
    return L - math.pi * 2 * int(L / (math.pi * 2))


def _sun_long_idx(day_number: int, tz: int) -> int:
    return int(_sun_long(day_number - 0.5 - tz / 24) / math.pi * 6)


def _new_moon_day(k: int, tz: int) -> int:
    return int(_new_moon(k) + 0.5 + tz / 24)


def _month11(yy: int, tz: int) -> int:
    off = _jd(31, 12, yy) - 2415021
    k = int(off / 29.530588853)
    nm = _new_moon_day(k, tz)
    if _sun_long_idx(nm, tz) >= 9:
        nm = _new_moon_day(k - 1, tz)
    return nm


def _leap_offset(a11: int, tz: int) -> int:
    k = int((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    i = 1
    arc = _sun_long_idx(_new_moon_day(k + i, tz), tz)
    while True:
        last = arc
        i += 1
        arc = _sun_long_idx(_new_moon_day(k + i, tz), tz)
        if arc == last or i >= 14:
            break
    return i - 1


def solar2lunar(dd: int, mm: int, yy: int, tz: int = 7) -> tuple[int, int, int, int]:
    """(ngày âm, tháng âm, năm âm, nhuận 0/1) của ngày dương dd/mm/yy."""
    day_number = _jd(dd, mm, yy)
    k = int((day_number - 2415021.076998695) / 29.530588853)
    ms = _new_moon_day(k + 1, tz)
    if ms > day_number:
        ms = _new_moon_day(k, tz)
    a11 = _month11(yy, tz)
    b11 = a11
    if a11 >= ms:
        ly = yy
        a11 = _month11(yy - 1, tz)
    else:
        ly = yy + 1
        b11 = _month11(yy + 1, tz)
    ld = day_number - ms + 1
    diff = int((ms - a11) / 29)
    leap = 0
    lm = diff + 11
    if b11 - a11 > 365:
        lo = _leap_offset(a11, tz)
        if diff >= lo:
            lm = diff + 10
            if diff == lo:
                leap = 1
    if lm > 12:
        lm -= 12
    if lm >= 11 and diff < 4:
        ly -= 1
    return ld, lm, ly, leap


def lunar_of(d: dt.date) -> tuple[int, int, int, int]:
    return solar2lunar(d.day, d.month, d.year)


def can_chi(ly: int) -> str:
    return f"{_CAN[(ly + 6) % 10]} {_CHI[(ly + 8) % 12]}"


def lunar_label(d: dt.date) -> str:
    """'28/7 ÂL Bính Ngọ' (tháng nhuận → '28/6N')."""
    ld, lm, ly, leap = lunar_of(d)
    return f"{ld}/{lm}{'N' if leap else ''} ÂL {can_chi(ly)}"


def find_solar(ld: int, lm: int, around: dt.date, span: int = 40) -> dt.date | None:
    """Ngày dương GẦN `around` nhất (±span ngày) có ngày/tháng âm = (ld, lm), ưu tiên
    tháng KHÔNG nhuận. Dùng để tìm 'cùng ngày âm lịch năm ngoái'."""
    best = None
    for off in range(-span, span + 1):
        d = around + dt.timedelta(days=off)
        a, b, _, leap = lunar_of(d)
        if a == ld and b == lm:
            if not leap:
                if best is None or abs(off) < abs((best - around).days):
                    best = d
            elif best is None:
                best = d
    return best


def next_lunar_event(ld: int, lm: int, start: dt.date, name: str) -> dict:
    """Sự kiện âm lịch KẾ TIẾP (≥ start): {'name','ymd','days'}."""
    for off in range(0, 420):
        d = start + dt.timedelta(days=off)
        a, b, _, leap = lunar_of(d)
        if a == ld and b == lm and not leap:
            return {"name": name, "ymd": d.isoformat(), "days": off}
    return {"name": name, "ymd": "", "days": -1}
