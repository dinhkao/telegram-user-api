"""Bảng `web_comments` (app.db) — schema + thêm/đọc bình luận theo thread_id đơn.

Connection qua utils.db (cổng chung). Dùng bởi: server_app/comment_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS web_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_web_comments_thread ON web_comments(thread_id, created_at)"


_ensured: set[str] = set()   # DDL chạy 1 lần mỗi path mỗi process — không tốn schema lock mỗi request


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        _ensured.add(key)
    return conn


def add_comment(thread_id: int, username: str, text: str, *, db_path: str | None = None) -> dict:
    """Thêm bình luận. Raise ValueError nếu text trống."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text trống")
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO web_comments (thread_id, username, text, created_at) VALUES (?, ?, ?, ?)",
            (int(thread_id), username or "?", text, now),
        )
        return {"id": cur.lastrowid, "thread_id": int(thread_id), "username": username or "?", "text": text, "created_at": now}
    finally:
        conn.close()


def list_comments(thread_id: int, *, db_path: str | None = None) -> list[dict]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, thread_id, username, text, created_at FROM web_comments WHERE thread_id = ? ORDER BY created_at ASC, id ASC",
            (int(thread_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
