"""Sổ quỹ (cash book): phiếu thu/chi -> shared SQLite (app.db).

schema (bảng quy_receipts) + queries (CRUD/summary) + domain (luật thuần).
Payment tiền mặt của đơn tạo 1 phiếu thu 'order' gắn order_thread_id + payment_id
(order_commands_v3._process_payment_core). Web API: server_app/quy_routes.py."""
from .schema import create_quy_table, migrate_quy_table
from .queries import (
    create_receipt,
    get_receipt,
    list_receipts,
    count_receipts,
    summary,
    list_by_order,
    delete_receipt,
    delete_by_payment,
    delete_by_batch,
)
from .domain import RECEIPT_TYPES, normalize_type, parse_amount, signed, compute_summary

__all__ = [
    "create_quy_table",
    "migrate_quy_table",
    "create_receipt",
    "get_receipt",
    "list_receipts",
    "count_receipts",
    "summary",
    "list_by_order",
    "delete_receipt",
    "delete_by_payment",
    "delete_by_batch",
    "RECEIPT_TYPES",
    "normalize_type",
    "parse_amount",
    "signed",
    "compute_summary",
]
