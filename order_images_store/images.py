"""Bảng `order_images` (app.db) — CRUD metadata ảnh đính kèm theo thread_id đơn.

Connection qua utils.db (cổng chung). File ảnh thật do server_app/image_routes ghi
xuống đĩa; ở đây chỉ lưu tên file + kích thước + người tải. Dùng bởi: image_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS order_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    thumb TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    uploaded_by TEXT NOT NULL DEFAULT '?',
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_order_images_thread ON order_images(thread_id, created_at)"

_ensured: set[str] = set()   # DDL chạy 1 lần mỗi path mỗi process — không tốn schema lock mỗi request


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        _ensured.add(key)
    return conn


def add_image(
    thread_id: int,
    filename: str,
    thumb: str,
    mime: str,
    *,
    size: int = 0,
    width: int = 0,
    height: int = 0,
    uploaded_by: str = "?",
    db_path: str | None = None,
) -> dict:
    """Ghi 1 dòng metadata ảnh; trả về dict đầy đủ (kèm id)."""
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO order_images (thread_id, filename, thumb, mime, size, width, height, uploaded_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(thread_id), filename, thumb, mime, int(size), int(width), int(height), uploaded_by or "?", now),
        )
        return {
            "id": cur.lastrowid, "thread_id": int(thread_id), "filename": filename, "thumb": thumb,
            "mime": mime, "size": int(size), "width": int(width), "height": int(height),
            "uploaded_by": uploaded_by or "?", "created_at": now,
        }
    finally:
        conn.close()


def list_images(thread_id: int, *, db_path: str | None = None) -> list[dict]:
    """Ảnh của 1 đơn, mới nhất trước."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, thread_id, filename, thumb, mime, size, width, height, uploaded_by, created_at"
            " FROM order_images WHERE thread_id = ? ORDER BY created_at DESC, id DESC",
            (int(thread_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_image(image_id: int, *, db_path: str | None = None) -> dict | None:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, thread_id, filename, thumb, mime, size, width, height, uploaded_by, created_at"
            " FROM order_images WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_image(image_id: int, thread_id: int, *, db_path: str | None = None) -> dict | None:
    """Xoá dòng nếu đúng thread_id; trả về dòng vừa xoá (để caller xoá file), None nếu không có."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, thread_id, filename, thumb FROM order_images WHERE id = ? AND thread_id = ?",
            (int(image_id), int(thread_id)),
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM order_images WHERE id = ?", (int(image_id),))
        return dict(row)
    finally:
        conn.close()
