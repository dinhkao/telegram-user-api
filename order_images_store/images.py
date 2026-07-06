"""Bảng `order_images` (app.db) — CRUD metadata ảnh đính kèm theo thread_id đơn.

Connection qua utils.db (cổng chung). File ảnh thật do server_app/image_routes ghi
xuống đĩa; ở đây chỉ lưu tên file + kích thước + người tải + id tin Telegram (để
đồng bộ 2 chiều, chống nhập trùng). Dùng bởi: image_routes, server_app/order_photo_sync.
"""
from __future__ import annotations

import time

from utils.db import get_connection

# Loại ảnh của đơn (phân loại thủ công + tự động cho hoá đơn). 'khac' = mặc định.
KINDS = ("soan_hang", "nop_tien", "hoa_don", "khac")
DEFAULT_KIND = "khac"


def norm_kind(kind: str | None) -> str:
    """Chuẩn hoá về 1 loại hợp lệ; giá trị lạ → mặc định."""
    k = (kind or "").strip().lower()
    return k if k in KINDS else DEFAULT_KIND


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
    kind TEXT NOT NULL DEFAULT 'khac',
    tg_message_id INTEGER,
    created_at INTEGER NOT NULL
)
"""
_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_order_images_thread ON order_images(thread_id, created_at)"

_COLS = "id, thread_id, filename, thumb, mime, size, width, height, uploaded_by, kind, tg_message_id, created_at"

_ensured: set[str] = set()   # DDL chạy 1 lần mỗi path mỗi process — không tốn schema lock mỗi request


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        # Migration: bảng cũ (bản đầu) chưa có cột tg_message_id → thêm nếu thiếu.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(order_images)").fetchall()}
        if "tg_message_id" not in cols:
            try:
                conn.execute("ALTER TABLE order_images ADD COLUMN tg_message_id INTEGER")
            except Exception:  # noqa: BLE001 — cột đã có ở process khác thì bỏ qua
                pass
        if "kind" not in cols:
            try:
                conn.execute("ALTER TABLE order_images ADD COLUMN kind TEXT NOT NULL DEFAULT 'khac'")
            except Exception:  # noqa: BLE001 — cột đã có ở process khác thì bỏ qua
                pass
        # Backstop chống nhập trùng: 1 tin Telegram (tg_message_id non-NULL) chỉ 1 ảnh/đơn.
        # NULL được coi là khác nhau trong UNIQUE → nhiều upload web (chưa forward) không đụng.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_order_images_tgmsg "
                "ON order_images(thread_id, tg_message_id)"
            )
        except Exception:  # noqa: BLE001 — có dòng trùng cũ thì bỏ qua, không chặn khởi động
            pass
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
    kind: str | None = None,
    tg_message_id: int | None = None,
    db_path: str | None = None,
) -> dict:
    """Ghi 1 dòng metadata ảnh; trả về dict đầy đủ (kèm id)."""
    now = int(time.time())
    kind = norm_kind(kind)
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO order_images (thread_id, filename, thumb, mime, size, width, height, uploaded_by, kind, tg_message_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(thread_id), filename, thumb, mime, int(size), int(width), int(height),
             uploaded_by or "?", kind, tg_message_id, now),
        )
        if cur.rowcount == 0 and tg_message_id is not None:
            # đã có ảnh cho tin Telegram này (race) → trả về dòng sẵn có, không tạo trùng
            row = conn.execute(
                f"SELECT {_COLS} FROM order_images WHERE thread_id = ? AND tg_message_id = ?",
                (int(thread_id), int(tg_message_id)),
            ).fetchone()
            if row:
                return dict(row)
        return {
            "id": cur.lastrowid, "thread_id": int(thread_id), "filename": filename, "thumb": thumb,
            "mime": mime, "size": int(size), "width": int(width), "height": int(height),
            "uploaded_by": uploaded_by or "?", "kind": kind, "tg_message_id": tg_message_id, "created_at": now,
        }
    finally:
        conn.close()


def update_kind(image_id: int, thread_id: int, kind: str, *, db_path: str | None = None) -> dict | None:
    """Đổi loại ảnh (soạn hàng / nộp tiền / hoá đơn / khác). Trả về dòng đã cập nhật, None nếu không có."""
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE order_images SET kind = ? WHERE id = ? AND thread_id = ?",
            (norm_kind(kind), int(image_id), int(thread_id)),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(f"SELECT {_COLS} FROM order_images WHERE id = ?", (int(image_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_images(thread_id: int, *, db_path: str | None = None) -> list[dict]:
    """Ảnh của 1 đơn, mới nhất trước."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            f"SELECT {_COLS} FROM order_images WHERE thread_id = ? ORDER BY created_at DESC, id DESC",
            (int(thread_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_image(image_id: int, *, db_path: str | None = None) -> dict | None:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            f"SELECT {_COLS} FROM order_images WHERE id = ?", (int(image_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def has_tg_message(thread_id: int, tg_message_id: int, *, db_path: str | None = None) -> bool:
    """Đã có ảnh nào của đơn ứng với tin Telegram này chưa (chống nhập trùng)."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM order_images WHERE thread_id = ? AND tg_message_id = ? LIMIT 1",
            (int(thread_id), int(tg_message_id)),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def set_tg_message_id(image_id: int, tg_message_id: int, *, db_path: str | None = None) -> None:
    """Gắn id tin Telegram vào dòng ảnh (sau khi forward web → topic thành công)."""
    conn = _conn(db_path)
    try:
        conn.execute("UPDATE order_images SET tg_message_id = ? WHERE id = ?", (int(tg_message_id), int(image_id)))
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
