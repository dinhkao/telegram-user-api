"""ENGINE dự báo hàng hoá — thuần (không IO), unit-tested (tests/test_forecast_engine.py).

`compute(lines, today, prev_day_forecast=None)` → dict số liệu cho HÔM NAY + TUẦN NÀY
(T2→CN chứa hôm nay), theo NHÓM sản phẩm (`fam`). Công thức mỗi nhóm:
  - w4avg  = trung bình tuần của 4 tuần TRỌN gần nhất (trước tuần này)
  - ngày   : base = w4avg × tỉ trọng THỨ trong tuần (8 tuần gần nhất, toàn kho)
             factor = 7 ngày quanh CÙNG NGÀY ÂM LỊCH năm ngoái ÷ trung bình 8 tuần quanh đó
  - tuần   : factor = CÙNG TUẦN ÂM LỊCH năm ngoái ÷ trung bình 4 tuần trước + 4 tuần sau
  - fc = base × (1 + factor)/2 (kẹp factor 0,7–1,5; nền năm ngoái < 15 → 1,0);
    hi = ×1,2 (ngày) / ×1,15 (tuần); tuần còn có sofar (đã bán T2→hôm nay) + remain.
Sự kiện âm lịch sắp tới (Trung thu 15/8, Tết 1/1) kèm số ngày. Đầu vào từ history.load_lines.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .lunar import can_chi, find_solar, lunar_label, lunar_of, next_lunar_event

_DOW = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
_MIN_BASE = 15.0
_CLIP = (0.7, 1.5)


def _in(lines, a: dt.date, b: dt.date):
    return [ln for ln in lines if a <= ln["date"] <= b]


def _by_fam(lines) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for ln in lines:
        out[ln["fam"]] += ln["sl"]
    return out


def _totals(lines) -> tuple[float, int]:
    return sum(ln["sl"] for ln in lines), len({ln["tid"] for ln in lines})


def _clip(x: float) -> float:
    return max(_CLIP[0], min(_CLIP[1], x))


def _factor(ly_qty: float, ly_base: float) -> float:
    if ly_base < _MIN_BASE:
        return 1.0
    return _clip(ly_qty / ly_base)


def _round10(x: float) -> float:
    return float(round(x / 10.0) * 10) if x >= 50 else float(round(x))


def compute(lines: list[dict], today: dt.date, prev_day_forecast: float | None = None) -> dict:
    mon = today - dt.timedelta(days=today.weekday())
    sun = mon + dt.timedelta(days=6)
    # nền: 4 tuần trọn trước tuần này; tỉ trọng thứ: 8 tuần
    w4 = _by_fam(_in(lines, mon - dt.timedelta(days=28), mon - dt.timedelta(days=1)))
    w4avg = {f: q / 4.0 for f, q in w4.items()}
    dow_q = [0.0] * 7
    for ln in _in(lines, mon - dt.timedelta(days=56), mon - dt.timedelta(days=1)):
        dow_q[ln["date"].weekday()] += ln["sl"]
    tot = sum(dow_q) or 1.0
    dow_share = [q / tot for q in dow_q]
    if sum(dow_q) == 0:
        dow_share = [1 / 7] * 7

    # tên/đơn vị mới nhất theo nhóm
    meta: dict[str, tuple[str, str]] = {}
    for ln in sorted(lines, key=lambda x: x["date"]):
        meta[ln["fam"]] = (ln["name"], ln["unit"])

    # ── cùng ngày âm lịch năm ngoái ─────────────────────────────────────────
    ld, lm, ly, leap = lunar_of(today)
    ly_day = find_solar(ld, lm, today - dt.timedelta(days=354))
    day_rows = []
    if ly_day:
        d7 = _by_fam(_in(lines, ly_day - dt.timedelta(days=3), ly_day + dt.timedelta(days=3)))
        d56 = _by_fam(_in(lines, ly_day - dt.timedelta(days=31), ly_day + dt.timedelta(days=31)))
        d_base = {f: q / 9.0 for f, q in d56.items()}   # 63 ngày = 9 cửa sổ 7 ngày
    else:
        d7, d_base = {}, {}
    share = dow_share[today.weekday()]
    for f, avg in w4avg.items():
        base = avg * share
        fac = _factor(d7.get(f, 0.0), d_base.get(f, 0.0))
        fc = base * (1 + fac) / 2
        if fc < 1:
            continue
        name, unit = meta.get(f, ("", ""))
        day_rows.append({"fam": f, "name": name, "unit": unit, "fc": _round10(fc),
                         "hi": _round10(fc * 1.2), "base": round(base, 1), "factor": round(fac, 2)})
    day_rows.sort(key=lambda r: -r["fc"])
    day_total = _round10(sum(r["fc"] for r in day_rows))

    # ── cùng tuần âm lịch năm ngoái ─────────────────────────────────────────
    mld, mlm, _, _ = lunar_of(mon)
    ly_mon = find_solar(mld, mlm, mon - dt.timedelta(days=354))
    week_rows = []
    if ly_mon:
        wk_ly = _by_fam(_in(lines, ly_mon, ly_mon + dt.timedelta(days=6)))
        pre = _by_fam(_in(lines, ly_mon - dt.timedelta(days=28), ly_mon - dt.timedelta(days=1)))
        post = _by_fam(_in(lines, ly_mon + dt.timedelta(days=7), ly_mon + dt.timedelta(days=34)))
        w_base = {f: (pre.get(f, 0.0) + post.get(f, 0.0)) / 8.0 for f in set(pre) | set(post)}
    else:
        wk_ly, w_base = {}, {}
    sofar = _by_fam(_in(lines, mon, today))
    for f, avg in w4avg.items():
        fac = _factor(wk_ly.get(f, 0.0), w_base.get(f, 0.0))
        fc = avg * (1 + fac) / 2
        if fc < 1:
            continue
        name, unit = meta.get(f, ("", ""))
        sf = sofar.get(f, 0.0)
        week_rows.append({"fam": f, "name": name, "unit": unit, "fc": _round10(fc),
                          "hi": _round10(fc * 1.15), "sofar": round(sf, 1),
                          "remain": _round10(max(fc - sf, 0.0)), "w4avg": round(avg, 1),
                          "factor": round(fac, 2)})
    week_rows.sort(key=lambda r: -r["fc"])
    week_total = _round10(sum(r["fc"] for r in week_rows))
    week_sofar = round(sum(r["sofar"] for r in week_rows), 1)

    # ── thực tế gần đây ─────────────────────────────────────────────────────
    last7 = []
    for i in range(7, 0, -1):
        d = today - dt.timedelta(days=i)
        q, n = _totals(_in(lines, d, d))
        last7.append({"ymd": d.isoformat(), "total": round(q), "orders": n})
    y = today - dt.timedelta(days=1)
    yq, yn = _totals(_in(lines, y, y))

    events = [next_lunar_event(15, 8, today, "Trung thu"), next_lunar_event(1, 1, today, "Tết")]
    return {
        "ymd": today.isoformat(), "dow_label": _DOW[today.weekday()],
        "lunar": {"d": ld, "m": lm, "y": ly, "leap": leap, "label": lunar_label(today),
                  "year_name": can_chi(ly)},
        "day": {"total": day_total, "hi": _round10(day_total * 1.2), "rows": day_rows,
                "ly_ymd": ly_day.isoformat() if ly_day else "", "dow_share": round(share, 3)},
        "week": {"from": mon.isoformat(), "to": sun.isoformat(), "total": week_total,
                 "hi": _round10(week_total * 1.15), "sofar": week_sofar,
                 "remain": _round10(max(week_total - week_sofar, 0.0)), "rows": week_rows,
                 "ly_from": ly_mon.isoformat() if ly_mon else "",
                 "w4avg_total": round(sum(w4avg.values()))},
        "yesterday": {"ymd": y.isoformat(), "total": round(yq), "orders": yn,
                      "forecast": prev_day_forecast},
        "last7": last7, "events": events,
    }
