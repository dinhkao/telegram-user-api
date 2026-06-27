from __future__ import annotations

from .core import DONHANG_PATH, _ref, log

_ORDER_SYNC_DISABLED_LOGGED = False


def get_order(thread_id: int | str) -> dict | None:
    r = _ref(f"{DONHANG_PATH}/{thread_id}")
    return None if r is None else r.get()


def set_order(thread_id: int | str, data: dict) -> bool:
    global _ORDER_SYNC_DISABLED_LOGGED
    if not _ORDER_SYNC_DISABLED_LOGGED:
        log.info("set_order: Firebase order sync disabled (SQLite-only mode)")
        _ORDER_SYNC_DISABLED_LOGGED = True
    return False


def update_order(thread_id: int | str, updates: dict) -> bool:
    return False
