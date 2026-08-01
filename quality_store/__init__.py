"""quality_store — BÁO CÁO CHẤT LƯỢNG MÂM KẸO hằng ngày (`tray_quality_reports`,
app.db, 100% local).

Nhân viên sản xuất chụp ảnh MÂM KẸO mình làm được mỗi ngày; dashboard cho biết thợ
nào đã/chưa chụp hôm nay. Thực thể = THỢ (bảng `production_workers` của worker_store
— KHÔNG tạo danh sách người thứ hai). Ảnh gắn vào TỪNG BÁO CÁO qua media scope
'quality_report' (1 báo cáo tính là "đã báo cáo" khi có ≥1 ảnh). DDL ensure
per-module (schema.py), logic thuần ở domain.py (dùng chung utils/daily_photo_report
với area_store). Dùng bởi server_app/quality_routes.
"""
from .reports import (
    get_or_create_report, get_report, list_reports, list_reports_since, soft_delete_report,
)
from .schema import ensure_tables

__all__ = [
    "ensure_tables",
    "get_or_create_report", "get_report", "list_reports", "list_reports_since", "soft_delete_report",
]
