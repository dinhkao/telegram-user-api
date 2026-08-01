"""Logic THUẦN cho báo cáo chất lượng mâm kẹo (KHÔNG IO, unit-tested).

Mốc ngày + ghép hàng dashboard dùng chung với báo cáo vệ sinh khu vực →
utils/daily_photo_report.py; file này chỉ chốt entity_key='worker_id' (thực thể =
THỢ trong bảng production_workers). Dùng bởi server_app.quality_routes.
"""
from __future__ import annotations

from utils.daily_photo_report import last_n_days, today_vn

__all__ = ["today_vn", "last_n_days", "build_dashboard_rows"]


def build_dashboard_rows(
    workers: list[dict],
    reports: list[dict],
    today_ymd: str,
    *,
    week: int = 7,
) -> tuple[list[dict], int]:
    """Ghép thợ + báo cáo chất lượng (mỗi báo cáo có 'photo_count') → hàng dashboard.
    Xem utils.daily_photo_report.build_dashboard_rows; báo cáo trỏ thợ qua 'worker_id'."""
    from utils.daily_photo_report import build_dashboard_rows as _build
    return _build(workers, reports, today_ymd, entity_key="worker_id", week=week)
