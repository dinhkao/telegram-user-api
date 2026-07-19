"""salary_store — lương THÁNG (phụ cấp/thưởng theo tháng, ứng lương, bảng lương tháng).

Tính live lương SP từ production_store; bảng riêng cho phụ cấp/thưởng + ứng. app.db.
"""
from salary_store.store import (
    ensure_schema,
    month_range,
    get_month_adjust,
    set_month_adjust,
    list_advances,
    advance_totals,
    add_advance,
    void_advance,
    list_allowances,
    allowance_totals,
    add_allowance,
    void_allowance,
    compute_month_payroll,
)

__all__ = [
    "ensure_schema", "month_range", "get_month_adjust", "set_month_adjust",
    "list_advances", "advance_totals", "add_advance", "void_advance",
    "list_allowances", "allowance_totals", "add_allowance", "void_allowance",
    "compute_month_payroll",
]
