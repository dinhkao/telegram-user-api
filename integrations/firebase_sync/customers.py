from __future__ import annotations

from .core import KHACH_HANG_PATH, _now_iso, _ref


def get_customer(thread_id: int | str) -> dict | None:
    r = _ref(f"{KHACH_HANG_PATH}/{thread_id}")
    return None if r is None else r.get()


def set_customer(thread_id: int | str, data: dict) -> bool:
    r = _ref(f"{KHACH_HANG_PATH}/{thread_id}")
    if r is None:
        return False
    data["updated_at"] = _now_iso()
    r.set(data)
    return True
