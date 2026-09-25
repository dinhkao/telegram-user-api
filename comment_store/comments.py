"""Bảng `web_comments` (app.db) — schema + thêm/đọc bình luận theo thread_id đơn.

Cột `topic` (NULL = chung): bình luận gửi từ khung trao đổi RIÊNG ở 1 khu của trang
chi tiết đơn (hoá đơn / xuất kho / giao hàng). Vẫn là CÙNG 1 luồng trao đổi của đơn —
khung chính hiện tất cả (kèm nhãn), khung khu vực chỉ lọc theo topic.

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


TOPICS = {"hoa_don": "Hoá đơn", "xuat_kho": "Xuất kho", "giao_hang": "Giao hàng"}

_ensured: set[str] = set()   # DDL chạy 1 lần mỗi path mỗi process — không tốn schema lock mỗi request


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(web_comments)").fetchall()}
        if "topic" not in cols:
            conn.execute("ALTER TABLE web_comments ADD COLUMN topic TEXT")
        _ensured.add(key)
    return conn


def add_comment(thread_id: int, username: str, text: str, *, topic: str | None = None,
                db_path: str | None = None) -> dict:
    """Thêm bình luận. Raise ValueError nếu text trống. topic lạ → coi như chung (None)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text trống")
    topic = topic if topic in TOPICS else None
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO web_comments (thread_id, username, text, created_at, topic) VALUES (?, ?, ?, ?, ?)",
            (int(thread_id), username or "?", text, now, topic),
        )
        return {"id": cur.lastrowid, "thread_id": int(thread_id), "username": username or "?", "text": text,
                "created_at": now, "topic": topic}
    finally:
        conn.close()


def list_comments(thread_id: int, *, db_path: str | None = None) -> list[dict]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, thread_id, username, text, created_at, topic FROM web_comments WHERE thread_id = ? ORDER BY created_at ASC, id ASC",
            (int(thread_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
