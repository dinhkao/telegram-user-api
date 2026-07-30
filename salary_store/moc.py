"""MỐC LƯƠNG THÁNG của thợ lương THỜI GIAN — lưu THEO TỪNG THÁNG.

Cột `salary_month.monthly_salary` (NULL = tháng đó KHÔNG đặt riêng). Vì sao không
để 1 số duy nhất trong hồ sơ thợ (`production_workers.monthly_salary`): mốc đổi
theo thời gian (tăng lương, đổi thoả thuận), 1 số chung nghĩa là sửa hôm nay thì
TÍNH LẠI CẢ QUÁ KHỨ → bảng lương tháng đã trả tiền tự đổi số. Luật:

- mốc HIỆU LỰC của tháng M = bản đặt gần nhất có tháng ≤ M (đặt tháng nào thì áp
  từ tháng đó TRỞ ĐI, tháng sau tự kế thừa nên khỏi nhập lại mỗi tháng),
- chưa có bản nào ≤ M → mốc mặc định ở hồ sơ thợ (dữ liệu trước khi có cột này),
- đặt/sửa mốc ở tháng M chỉ đổi M trở đi — tháng TRƯỚC M không bao giờ đổi.

Nối: salary_store.store (bảng salary_month + compute_month_payroll), utils.db.
Client: webapp/src/detail/payrollActions.ts (ô Mốc bảng lương tháng).
"""
from __future__ import annotations

from utils.db import transaction


def month_moc_map(conn, ym: str) -> dict[int, dict]:
    """{worker_id: {'value': mốc, 'ym': tháng ĐẶT mốc đó}} — mốc hiệu lực của tháng
    `ym`. Thợ chưa có bản nào ≤ ym thì KHÔNG có khoá (gọi phải tự lùi về mốc hồ sơ)."""
    rows = conn.execute(
        "SELECT worker_id, ym, monthly_salary FROM salary_month "
        "WHERE monthly_salary IS NOT NULL AND ym <= ? ORDER BY worker_id, ym",
        (ym,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:   # ym tăng dần → bản sau ghi đè bản trước, còn lại = gần nhất
        out[r["worker_id"]] = {"value": float(r["monthly_salary"] or 0), "ym": r["ym"]}
    return out


def set_month_moc(conn, ym: str, worker_id: int, value: float | None, by: str = "") -> None:
    """Đặt mốc RIÊNG cho (tháng, thợ). value None hoặc ≤ 0 = BỎ mốc riêng tháng này
    → tháng đó kế thừa mốc gần nhất trước đó (hoặc mốc hồ sơ thợ). Chỉ ghi đúng cột
    monthly_salary — thưởng/ghi chú/lương tuần của tháng giữ nguyên."""
    v = None if value is None or float(value) <= 0 else float(value)
    with transaction(conn):
        conn.execute(
            "INSERT INTO salary_month (ym, worker_id, monthly_salary, updated_at, updated_by) "
            "VALUES (?, ?, ?, datetime('now','+7 hours'), ?) "
            "ON CONFLICT(ym, worker_id) DO UPDATE SET monthly_salary = excluded.monthly_salary, "
            "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (ym, worker_id, v, by or ""),
        )


def list_worker_moc(conn, worker_id: int) -> list[dict]:
    """Lịch sử mốc đã đặt của 1 thợ (tháng tăng dần) — để UI nói rõ mốc có từ tháng nào."""
    rows = conn.execute(
        "SELECT ym, monthly_salary, updated_at, updated_by FROM salary_month "
        "WHERE worker_id = ? AND monthly_salary IS NOT NULL ORDER BY ym",
        (worker_id,),
    ).fetchall()
    return [{"ym": r["ym"], "value": float(r["monthly_salary"] or 0),
             "at": r["updated_at"] or "", "by": r["updated_by"] or ""} for r in rows]
