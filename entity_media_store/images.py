"""Bảng `entity_images` (app.db) — metadata ảnh theo (scope, entity_id).

Generic cho production slip / box… (khác order_images). Bytes ảnh nằm trên disk
(ORDER_MEDIA_DIR/<scope>/<entity_id>/), bảng này chỉ giữ metadata. KHÔNG có
tg_message_id (web-only, không sync Telegram). Dùng bởi server_app/entity_media_routes.
"""
from __future__ import annotations

import time

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entity_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    thumb TEXT NOT NULL,
    mime TEXT,
    size INTEGER,
    width INTEGER,
    height INTEGER,
    uploaded_by TEXT,
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_entity_images ON entity_images(scope, entity_id, created_at)"

_ensured: set[str] = set()


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        _ensured.add(key)
    return conn


def add_image(scope: str, entity_id: int, filename: str, thumb: str, mime: str, *,
              size: int = 0, width: int = 0, height: int = 0, uploaded_by: str = "?",
              db_path: str | None = None) -> dict:
    now = int(time.time())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO entity_images (scope, entity_id, filename, thumb, mime, size, width, height, uploaded_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scope, int(entity_id), filename, thumb, mime, int(size), int(width), int(height), uploaded_by or "?", now),
        )
        return {"id": cur.lastrowid, "scope": scope, "entity_id": int(entity_id), "filename": filename,
                "thumb": thumb, "mime": mime, "size": int(size), "width": int(width), "height": int(height),
                "uploaded_by": uploaded_by or "?", "created_at": now}
    finally:
        conn.close()


def list_images(scope: str, entity_id: int, *, db_path: str | None = None) -> list[dict]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, filename, thumb, mime, size, width, height, uploaded_by, created_at"
            " FROM entity_images WHERE scope = ? AND entity_id = ? ORDER BY created_at DESC, id DESC",
            (scope, int(entity_id)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_image(image_id: int, *, db_path: str | None = None) -> dict | None:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, scope, entity_id, filename, thumb, mime FROM entity_images WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_image(image_id: int, scope: str, entity_id: int, *, db_path: str | None = None) -> dict | None:
    """Xoá 1 dòng ảnh (đúng scope+entity), trả về row (để caller unlink file). None nếu không có."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, filename, thumb FROM entity_images WHERE id = ? AND scope = ? AND entity_id = ?",
            (int(image_id), scope, int(entity_id)),
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM entity_images WHERE id = ?", (int(image_id),))
        return dict(row)
    finally:
        conn.close()
