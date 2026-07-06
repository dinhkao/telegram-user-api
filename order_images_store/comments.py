"""Bảng `order_image_comments` (app.db) — bình luận gắn theo TỪNG ảnh của đơn.

Khác `web_comments` (bình luận cấp đơn): ở đây khoá theo image_id để hiện trong
trình xem ảnh (PhotoViewer). Connection qua utils.db. Dùng bởi: server_app/image_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS order_image_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_order_image_comments_img ON order_image_comments(image_id, created_at)"

_ensured: set[str] = set()   # DDL 1 lần / path / process


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        _ensured.add(key)
    return conn


def add_image_comment(image_id: int, thread_id: int, username: str, text: str, *, db_path: str | None = None) -> dict:
    """Thêm bình luận cho 1 ảnh. Raise ValueError nếu text trống."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text trống")
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO order_image_comments (image_id, thread_id, username, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (int(image_id), int(thread_id), username or "?", text, now),
        )
        return {"id": cur.lastrowid, "image_id": int(image_id), "thread_id": int(thread_id),
                "username": username or "?", "text": text, "created_at": now}
    finally:
        conn.close()


def list_image_comments(image_id: int, *, db_path: str | None = None) -> list[dict]:
    """Bình luận của 1 ảnh, cũ → mới (đọc như hội thoại)."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, image_id, thread_id, username, text, created_at FROM order_image_comments"
            " WHERE image_id = ? ORDER BY created_at ASC, id ASC",
            (int(image_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_image_comment(comment_id: int, image_id: int, *, db_path: str | None = None) -> bool:
    """Xoá 1 bình luận (đúng image_id). True nếu có xoá."""
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM order_image_comments WHERE id = ? AND image_id = ?",
            (int(comment_id), int(image_id)),
        )
        return cur.rowcount > 0
    finally:
        conn.close()
