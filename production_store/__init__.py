"""Production-slip ("phieu SX") store: schema + queries -> shared SQLite."""
from .schema import create_production_table, migrate_production_table
from .queries import (
    get_slip,
    list_slips,
    count_slips,
    upsert_slip,
    set_sp,
    set_slip_wage,
    set_target,
    set_note,
    set_lock_override,
    set_kind,
    add_number,
    set_total,
    remove_number_by_note,
    set_bang,
    delete_slip,
)

__all__ = [
    "create_production_table",
    "migrate_production_table",
    "get_slip",
    "list_slips",
    "count_slips",
    "upsert_slip",
    "set_sp",
    "set_slip_wage",
    "set_target",
    "set_note",
    "set_lock_override",
    "set_kind",
    "add_number",
    "set_total",
    "remove_number_by_note",
    "set_bang",
    "delete_slip",
]
