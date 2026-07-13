"""Khoá kiểm kho theo NGƯỜI, theo dõi heartbeat riêng cho từng máy/tab."""
from __future__ import annotations

import time

LOCK_TTL = 60.0
_locks: dict[int, dict] = {}


def _user_key(user: str | None) -> str:
    return " ".join(str(user or "").strip().casefold().split())


def _same_user(lock: dict | None, user: str | None) -> bool:
    return bool(lock and (lock.get("user_key") or _user_key(lock.get("user"))) == _user_key(user))


def _session_key(sid: str | None) -> str:
    return str(sid or "__legacy__")


def lock_info(stocktake_id: int) -> dict | None:
    lock = _locks.get(stocktake_id)
    if not lock:
        return None
    now = time.monotonic()
    sessions = lock.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {_session_key(lock.get("sid")): float(lock.get("at") or 0)}
    sessions = {key: float(at or 0) for key, at in sessions.items() if now - float(at or 0) < LOCK_TTL}
    if not sessions:
        _locks.pop(stocktake_id, None)
        from server_app.realtime import emit_stocktake_lock
        emit_stocktake_lock(stocktake_id, None)
        return None
    lock["sessions"] = sessions
    lock["at"] = max(sessions.values())
    return lock


def acquire(stocktake_id: int, user: str, sid: str) -> tuple[bool, str | None]:
    lock = lock_info(stocktake_id)
    if lock and not _same_user(lock, user):
        return False, str(lock.get("user") or "Người khác")
    was_free = lock is None
    now = time.monotonic()
    if was_free:
        lock = {"user": user, "user_key": _user_key(user), "sessions": {}}
        _locks[stocktake_id] = lock
    lock["sessions"][_session_key(sid)] = now
    lock["at"] = now
    if was_free:
        from server_app.realtime import emit_stocktake_lock
        emit_stocktake_lock(stocktake_id, user)
    return True, str(lock.get("user") or user)


def held_by(stocktake_id: int, user: str, sid: str) -> tuple[bool, str | None]:
    lock = lock_info(stocktake_id)
    mine = bool(lock and _same_user(lock, user) and _session_key(sid) in lock.get("sessions", {}))
    return mine, (str(lock.get("user")) if lock else None)


def release(stocktake_id: int, user: str | None = None, sid: str = "", *, force: bool = False) -> bool:
    lock = lock_info(stocktake_id)
    if not lock:
        return False
    if not force:
        key = _session_key(sid)
        if not _same_user(lock, user) or key not in lock.get("sessions", {}):
            return False
        lock["sessions"].pop(key, None)
        if lock["sessions"]:
            lock["at"] = max(lock["sessions"].values())
            return True
    _locks.pop(stocktake_id, None)
    from server_app.realtime import emit_stocktake_lock
    emit_stocktake_lock(stocktake_id, None)
    return True
