"""salary_store — lương THÁNG (phụ cấp/thưởng theo tháng, ứng lương, bảng lương tháng).

Tính live lương SP từ production_store; bảng riêng cho phụ cấp/thưởng + ứng. app.db.
"""
from salary_store.allowance_calc import (
    allowance_amount,
    calc_label,
)
from salary_store.bonus import (
    THUONG_CHUYEN_CAN,
    THUONG_VE_SINH_MOI_NGAY,
    bonus_amounts,
)
from salary_store.bhxh import (
    list_worker_bhxh,
    month_bhxh_map,
    set_month_bhxh,
)
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
    allowance_rows_by_worker,
    add_allowance,
    update_allowance_note,
    void_allowance,
    compute_month_payroll,
)

__all__ = [
    "ensure_schema", "month_range", "get_month_adjust", "set_month_adjust",
    "list_advances", "advance_totals", "add_advance", "update_advance_note", "void_advance",
    "list_allowances", "allowance_rows_by_worker", "add_allowance", "update_allowance_note",
    "void_allowance", "compute_month_payroll",
    # mốc lương tháng theo TỪNG THÁNG (salary_store/moc.py)
    "month_moc_map", "set_month_moc", "list_worker_moc",
    # TRỪ BHXH theo tháng, cùng luật kế thừa với mốc (salary_store/bhxh.py)
    "month_bhxh_map", "set_month_bhxh", "list_worker_bhxh",
    # 2 khoản thưởng bật/tắt theo tháng (salary_store/bonus.py)
    "bonus_amounts", "THUONG_CHUYEN_CAN", "THUONG_VE_SINH_MOI_NGAY",
    # phụ cấp theo CÔNG THỨC (% lương gốc / đơn giá × ngày công)
    "allowance_amount", "calc_label",
]
