"""Danh sách thợ dùng chung cho báo cáo phiếu SX — bảng `production_workers`
trong shared app.db. Thợ có cờ is_default (thợ mặc định → template báo cáo).
Nối: utils.db (get_connection/transaction). Dùng bởi server_app/worker_routes.
"""
from .store import (
    ensure_table,
    list_workers,
    default_names,
    add_worker,
    update_worker,
    reorder_workers,
    delete_worker,
)

__all__ = [
    "ensure_table",
    "list_workers",
    "default_names",
    "add_worker",
    "update_worker",
    "reorder_workers",
    "delete_worker",
]
