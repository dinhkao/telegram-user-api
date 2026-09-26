"""TĂNG CA thợ lương SẢN PHẨM tính từ GIỜ GHI TRONG PHIẾU SX (không dùng máy chấm công). Thuần.

Luật (Duy chốt 2026-09-26):
- Ngày thường: giờ KẾT THÚC MUỘN NHẤT trong ngày của thợ (qua các phiếu thợ có sản
  lượng) phải SAU 17:15 thì mới có tăng ca; khi có thì đếm TỪ 17:00 (17:30 → 30 phút).
  Xét theo NGÀY chứ không từng phiếu: 16:10–17:10 + 17:10–17:30 → phiếu đầu góp 10'.
  Chỉ buổi chiều — lố trưa (sau 11h) KHÔNG tính.
- CHỦ NHẬT: toàn bộ sản lượng là tăng ca (giống máy chấm công coi CN là tăng ca).
- Tiền (cách B): số cây làm trong giờ tăng ca × đơn giá × 20% — CỘNG THÊM, số cây đó
  vẫn được trả 100% như thường. Số cây tăng ca = cây của phiếu × tỉ lệ thời gian phiếu
  nằm trong giờ tăng ca (ước tính theo thời gian, phiếu không ghi giờ cây theo giờ).
- Chỉ dòng tính tiền theo CÂY; dòng lương theo GIỜ (so_gio) không có phụ trội.
- Áp từ ngày báo cáo `OT_SINCE` — phiếu cũ hơn không đổi.
Phiếu thiếu giờ bắt đầu/kết thúc (hoặc kết thúc ≤ bắt đầu) ngày thường → 0.

Dùng bởi production_store.report_slips.compute_range_report (bảng lương, phiếu báo cáo,
bảng lương ngày), server_app.production_wages (#/tien-cong + khối tiền phiếu SX).
Client gương nhỏ (chỉ để GỢI Ý ở ô giờ): webapp/src/pages/ProductionReportEdit.tsx.
"""
from __future__ import annotations

from attendance_store.domain import OT_GRACE_MIN, SHIFT_WINDOWS, is_sunday
from production_store.time_fmt import time_minutes

OT_START_MIN = SHIFT_WINDOWS[1][1]   # 17:00 — hết ca chiều, cùng mốc máy chấm công
OT_PCT = 0.2                          # phụ trội +20% đơn giá cho cây làm trong giờ tăng ca
OT_SINCE = "2026-09-01"               # ngày báo cáo (YYYY-MM-DD) bắt đầu áp dụng


def slip_overtime(start, end, day_end_min: int | None, sunday: bool) -> tuple[int, float]:
    """(phút tăng ca của phiếu, tỉ lệ thời gian phiếu nằm trong giờ tăng ca 0..1)."""
    s, e = time_minutes(start), time_minutes(end)
    dur = e - s if s is not None and e is not None and e > s else 0
    if sunday:
        return dur, 1.0
    if not dur or day_end_min is None or day_end_min <= OT_START_MIN + OT_GRACE_MIN:
        return 0, 0.0
    ot = max(0, e - max(s, OT_START_MIN))
    return ot, ot / dur


def overtime_map(entries, times: dict, since: str = OT_SINCE) -> dict:
    """entries = [(thread_id, ymd 'YYYY-MM-DD', thợ)] — CHỈ dòng có sản lượng;
    times = {thread_id: (start, end)} → {(thread_id, thợ): (phút TC, tỉ lệ)} (chỉ khoá > 0)."""
    entries = [(t, y, w) for t, y, w in entries if y and y >= since]
    day_end: dict = {}
    for tid, ymd, wk in entries:
        e = time_minutes((times.get(tid) or ("", ""))[1])
        if e is not None:
            k = (ymd, wk)
            day_end[k] = max(day_end.get(k, e), e)
    out: dict = {}
    for tid, ymd, wk in entries:
        st, en = times.get(tid) or ("", "")
        mins, frac = slip_overtime(st, en, day_end.get((ymd, wk)), is_sunday(ymd))
        if frac > 0:
            out[(tid, wk)] = (mins, frac)
    return out


def ot_money(cay_piece: float, wage: float, frac: float) -> int:
    """Tiền phụ trội tăng ca = cây tính tiền × đơn giá × tỉ lệ TC × 20%."""
    return round(float(cay_piece or 0) * float(wage or 0) * float(frac or 0) * OT_PCT)
