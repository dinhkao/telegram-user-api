"""TRỪ BHXH theo tháng — khoản TRỪ cố định hằng tháng (BHXH/BHYT/BHTN phần NV đóng).

Cột `salary_month.bhxh` (NULL = tháng đó KHÔNG đặt riêng). Cùng luật KẾ THỪA với mốc
lương (salary_store/moc.py) vì cùng bản chất: 1 con số cố định tháng này qua tháng
khác, chỉ đổi khi mức đóng đổi — bắt văn phòng gõ lại mỗi tháng cho từng thợ là toil,
mà để 1 số duy nhất trong hồ sơ thợ thì sửa hôm nay lại TÍNH LẠI CẢ QUÁ KHỨ (bảng
lương đã trả tiền tự đổi số). Luật:

- số HIỆU LỰC của tháng M = bản đặt gần nhất có tháng ≤ M (đặt tháng nào áp từ tháng
  đó TRỞ ĐI, tháng sau tự kế thừa),
- chưa có bản nào ≤ M → 0 (không trừ),
- đặt/sửa ở tháng M chỉ đổi M trở đi — tháng TRƯỚC M không bao giờ đổi.

⚠ KHÁC mốc lương ở chỗ số 0: mốc lương dùng 0 = "bỏ đặt riêng tháng này", còn ở đây
0 là số CÓ NGHĨA ("từ tháng này thôi đóng BHXH") nên phải phân biệt:
- value = 0 hoặc số dương → ĐẶT RIÊNG tháng đó (0 = dừng trừ từ tháng này trở đi),
- value = None            → BỎ đặt riêng tháng đó → kế thừa lại bản trước.

Nối: salary_store.store (bảng salary_month + compute_month_payroll), utils.db.
Client: webapp/src/detail/payrollActions.ts (ô BHXH bảng lương tháng).
"""
from __future__ import annotations

from utils.db import transaction


def month_bhxh_map(conn, ym: str) -> dict[int, dict]:
    """{worker_id: {'value': số trừ, 'ym': tháng ĐẶT số đó}} — số hiệu lực của tháng
    `ym`. Thợ chưa có bản nào ≤ ym thì KHÔNG có khoá (gọi phải hiểu là 0)."""
    rows = conn.execute(
        "SELECT worker_id, ym, bhxh FROM salary_month "
        "WHERE bhxh IS NOT NULL AND ym <= ? ORDER BY worker_id, ym",
        (ym,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:   # ym tăng dần → bản sau ghi đè bản trước, còn lại = gần nhất
        out[r["worker_id"]] = {"value": float(r["bhxh"] or 0), "ym": r["ym"]}
    return out


def set_month_bhxh(conn, ym: str, worker_id: int, value: float | None, by: str = "") -> None:
    """Đặt số trừ BHXH RIÊNG cho (tháng, thợ). value None = BỎ đặt riêng tháng này →
    kế thừa bản gần nhất trước đó; value 0 = ĐẶT RIÊNG bằng 0 (dừng trừ từ tháng này
    trở đi) — 2 việc KHÁC nhau, xem docstring module. Số âm bị ép về 0. Chỉ ghi đúng
    cột bhxh — thưởng/ghi chú/lương tuần/mốc của tháng giữ nguyên."""
    v = None if value is None else max(0.0, float(value))
    with transaction(conn):
        conn.execute(
            "INSERT INTO salary_month (ym, worker_id, bhxh, updated_at, updated_by) "
            "VALUES (?, ?, ?, datetime('now','+7 hours'), ?) "
            "ON CONFLICT(ym, worker_id) DO UPDATE SET bhxh = excluded.bhxh, "
            "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (ym, worker_id, v, by or ""),
        )


def list_worker_bhxh(conn, worker_id: int) -> list[dict]:
    """Lịch sử số trừ BHXH đã đặt của 1 thợ (tháng tăng dần) — để UI nói rõ số có từ
    tháng nào."""
    rows = conn.execute(
        "SELECT ym, bhxh, updated_at, updated_by FROM salary_month "
        "WHERE worker_id = ? AND bhxh IS NOT NULL ORDER BY ym",
        (worker_id,),
    ).fetchall()
    return [{"ym": r["ym"], "value": float(r["bhxh"] or 0),
             "at": r["updated_at"] or "", "by": r["updated_by"] or ""} for r in rows]
