"""Kho thùng ("inventory_boxes") store: schema + queries + domain thuần → app.db.

Pool tồn kho gom theo product_code (gộp mọi phiếu SX). Nhập thùng từ phiếu SX,
xuất thùng cho đơn hàng. Xem docs/CLAUDE.md §4.
"""
from .schema import create_inventory_table, migrate_inventory_table
from .queries import (
    add_boxes,
    list_boxes,
    product_totals,
    product_summary,
    get_box,
    allocate_boxes,
    release_boxes,
    update_box,
    delete_box,
)
from .domain import group_by_size, summarize, next_box_code, format_box_code, parse_box_seq

__all__ = [
    "create_inventory_table",
    "migrate_inventory_table",
    "add_boxes",
    "list_boxes",
    "product_totals",
    "product_summary",
    "get_box",
    "allocate_boxes",
    "release_boxes",
    "update_box",
    "delete_box",
    "group_by_size",
    "summarize",
    "next_box_code",
    "format_box_code",
    "parse_box_seq",
]
