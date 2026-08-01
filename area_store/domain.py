"""Logic THUẦN cho khu vực xưởng + báo cáo vệ sinh (KHÔNG IO, unit-tested).

Mốc ngày + ghép hàng dashboard dùng chung với báo cáo chất lượng mâm kẹo →
utils/daily_photo_report.py; file này chỉ chốt entity_key='area_id'. Dùng bởi
area_store.reports/queries và server_app.area_routes.
"""
from __future__ import annotations

from utils.daily_photo_report import last_n_days, today_vn

__all__ = ["today_vn", "last_n_days", "build_dashboard_rows"]


def build_dashboard_rows(
    areas: list[dict],
    reports: list[dict],
    today_ymd: str,
    *,
    week: int = 7,
) -> tuple[list[dict], int]:
    """Ghép khu vực + báo cáo vệ sinh (mỗi báo cáo có 'photo_count') → hàng dashboard.
    Xem utils.daily_photo_report.build_dashboard_rows; báo cáo trỏ khu vực qua 'area_id'."""
    from utils.daily_photo_report import build_dashboard_rows as _build
    return _build(areas, reports, today_ymd, entity_key="area_id", week=week)
