"""Bảng `web_users` trong app.db (SHARED_DB_PATH) — schema + ensure.

Connection qua utils.db (cổng SQLite trung tâm). Dùng bởi: user_store.users.
"""
from __future__ import annotations

from utils.db import get_connection, transaction

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS web_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    pin_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'staff',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""


_ensured: set[str] = set()   # DDL chạy 1 lần mỗi path mỗi process — không tốn schema lock mỗi request


def get_users_conn(path: str | None = None):
    """Mở connection app.db (hoặc `path` cho test) và đảm bảo bảng tồn tại."""
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        _ensured.add(key)
    return conn


__all__ = ["get_users_conn", "transaction"]
