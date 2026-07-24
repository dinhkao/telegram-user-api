"""area_store — KHU VỰC XƯỞNG (`workshop_areas`) + BÁO CÁO VỆ SINH hằng ngày
(`area_hygiene_reports`) trong app.db (100% local).

Nhân viên chụp ảnh báo cáo vệ sinh từng khu vực mỗi ngày; dashboard cho biết khu
nào đã/chưa báo cáo hôm nay. Ảnh gắn vào TỪNG BÁO CÁO qua media scope 'area_report'
(1 báo cáo tính là "đã báo cáo" khi có ≥1 ảnh). DDL ensure per-module (schema.py),
logic thuần ở domain.py (unit-tested). Dùng bởi server_app/area_routes.
"""
from .queries import add_area, get_area, list_areas, soft_delete_area, update_area
from .reports import (
    get_or_create_report, get_report, list_reports, list_reports_since, soft_delete_report,
)
from .schema import ensure_tables

__all__ = [
    "ensure_tables",
    "add_area", "get_area", "list_areas", "soft_delete_area", "update_area",
    "get_or_create_report", "get_report", "list_reports", "list_reports_since", "soft_delete_report",
]
