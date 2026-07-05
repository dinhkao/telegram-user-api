"""Bảng `entity_comments` (app.db) — bình luận theo (scope, entity_id).

Generic cho production slip / box… (khác web_comments của order). Connection qua
utils.db. Dùng bởi: server_app/entity_media_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entity_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_entity_comments ON entity_comments(scope, entity_id, created_at)"

_ensured: set[str] = set()


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        _ensured.add(key)
    return conn


def add_comment(scope: str, entity_id: int, username: str, text: str, *, db_path: str | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("text trống")
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO entity_comments (scope, entity_id, username, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (scope, int(entity_id), username or "?", text, now),
        )
        return {"id": cur.lastrowid, "scope": scope, "entity_id": int(entity_id), "username": username or "?", "text": text, "created_at": now}
    finally:
        conn.close()


def list_comments(scope: str, entity_id: int, *, db_path: str | None = None) -> list[dict]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, text, created_at FROM entity_comments WHERE scope = ? AND entity_id = ? ORDER BY created_at ASC, id ASC",
            (scope, int(entity_id)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
