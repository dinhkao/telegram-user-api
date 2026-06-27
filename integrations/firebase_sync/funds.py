from __future__ import annotations

from .core import _ref


def set_fund_receipt(receipt_id: str, data: dict) -> bool:
    r = _ref(f"quy/phieu_thu_chi/{receipt_id}")
    if r is None:
        return False
    r.set(data)
    return True


def get_fund_receipts() -> dict:
    r = _ref("quy/phieu_thu_chi")
    return {} if r is None else (r.get() or {})
