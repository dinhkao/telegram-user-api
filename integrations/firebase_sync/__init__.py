from . import core as _core
from .core import DONHANG_PATH, KHACH_HANG_PATH, _get_app, _now_iso, log
from .customers import get_customer, set_customer
from .funds import get_fund_receipts, set_fund_receipt
from .orders import get_order, set_order, update_order

__all__ = [
    "DONHANG_PATH", "KHACH_HANG_PATH", "_get_app", "_ref", "_now_iso", "log",
    "get_customer", "set_customer", "get_fund_receipts", "set_fund_receipt",
    "get_order", "set_order", "update_order",
]


def __getattr__(name):
    if name == "firebase_app":
        return _core.firebase_app
    if name == "_ref":
        return _core._ref
    raise AttributeError(name)
