"""Kho thùng ("inventory_boxes") store: schema + queries + domain thuần → app.db.

Pool tồn kho gom theo product_code (gộp mọi phiếu SX). Nhập thùng từ phiếu SX,
xuất 1 phần thùng cho đơn hàng (box_allocations — thùng KHÔNG tách, chỉ giảm phần
còn lại). Xem docs/CLAUDE.md §4.
"""
from .schema import create_inventory_table, migrate_inventory_table
from .queries import (
    add_boxes,
    list_boxes,
    product_totals,
    product_summary,
    get_box,
    update_box,
    set_disabled,
    delete_box,
)
from .allocations import (
    create_allocations_table,
    migrate_legacy_allocations,
    allocate_picks,
    list_order_allocations,
    list_box_allocations,
    get_allocation,
    delete_allocation,
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
    "update_box",
    "set_disabled",
    "delete_box",
    "create_allocations_table",
    "migrate_legacy_allocations",
    "allocate_picks",
    "list_order_allocations",
    "list_box_allocations",
    "get_allocation",
    "delete_allocation",
    "group_by_size",
    "summarize",
    "next_box_code",
    "format_box_code",
    "parse_box_seq",
]
