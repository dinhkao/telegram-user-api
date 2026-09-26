"""Chuẩn hoá GIỜ bắt đầu/xong của báo cáo phiếu SX về 1 format "HH:MM" (24h). Thuần.

Dùng bởi `domain.parse_report` (mọi đường lưu báo cáo: webapp + lệnh Telegram),
sắp xếp phiếu theo giờ (`wage_pivot`, `report_slips`) và tool chạy bù dữ liệu cũ
`tools/backfill_production_times.py`. Client có bản GƯƠNG `webapp/src/format.ts::
normTime` — đổi luật phải đổi CẢ HAI.

Các kiểu thợ đã ghi (thực tế trong DB): "07:00" · "7:04" · "7h" · "13h40" · "9h5"
(= 09:05, phút 1 chữ số là PHÚT chứ không phải chục phút) · "13g40" · "13h 30" ·
"15h35p" · "1415" · "10" · "15:00_" · "7.30". Giờ 1–6 là buổi CHIỀU viết tắt
("4h15" → 16:15, "1" → 13:00) vì xưởng chỉ làm 7h–18h — đã soi toàn bộ dữ liệu cũ
kiểu "HH:MM": không có giờ nào < 7.
"""
from __future__ import annotations

import re

_SEP_RE = re.compile(r"^(\d{1,2})(?:[:hg.,](\d{1,2})?)?$")
_PM_MAX = 6   # giờ 1..6 = buổi chiều viết tắt


def normalize_time(value) -> str:
    """"7h5" → "07:05", "4h15" → "16:15". Rỗng → "". Không hiểu được → giữ NGUYÊN
    chuỗi gốc (đã strip) để không mất dữ liệu; `is_time_ok` báo cho UI tô đỏ."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    t = re.sub(r"\s+", "", raw.lower()).rstrip("_'\"")
    t = re.sub(r"(ph|p)$", "", t)
    if t.isdigit() and len(t) in (3, 4):
        h_s, m_s = t[:-2], t[-2:]
    else:
        m = _SEP_RE.match(t)
        if not m:
            return raw
        h_s, m_s = m.group(1), m.group(2) or "0"
    h, mi = int(h_s), int(m_s)
    if 1 <= h <= _PM_MAX:
        h += 12
    if h > 23 or mi > 59:
        return raw
    return f"{h:02d}:{mi:02d}"


def is_time_ok(value) -> bool:
    """Rỗng hoặc đã đúng "HH:MM" hợp lệ."""
    s = str(value or "").strip()
    return not s or normalize_time(s) == s and len(s) == 5 and s[2] == ":"


def time_minutes(value) -> int | None:
    """Phút trong ngày (để SẮP XẾP) — None khi rỗng/không hiểu."""
    s = normalize_time(value)
    if len(s) != 5 or s[2] != ":":
        return None
    return int(s[:2]) * 60 + int(s[3:])
