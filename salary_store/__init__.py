"""salary_store — lương THÁNG (phụ cấp/thưởng theo tháng, ứng lương, bảng lương tháng).

Tính live lương SP từ production_store; bảng riêng cho phụ cấp/thưởng + ứng. app.db.
"""
from salary_store.moc import (
    list_worker_moc,
    month_moc_map,
    set_month_moc,
)
from salary_store.store import (
    ensure_schema,
    month_range,
    get_month_adjust,
    set_month_adjust,
    list_advances,
    advance_totals,
    add_advance,
    update_advance_note,
    void_advance,
    list_allowances,
    allowance_totals,
    add_allowance,
    update_allowance_note,
    void_allowance,
    compute_month_payroll,
)

__all__ = [
    "ensure_schema", "month_range", "get_month_adjust", "set_month_adjust",
    "list_advances", "advance_totals", "add_advance", "update_advance_note", "void_advance",
    "list_allowances", "allowance_totals", "add_allowance", "update_allowance_note",
    "void_allowance", "compute_month_payroll",
    # mốc lương tháng theo TỪNG THÁNG (salary_store/moc.py)
    "month_moc_map", "set_month_moc", "list_worker_moc",
]
