"""CRUD + verify login cho bảng `web_users` (app.db).

IO mỏng — logic băm PIN nằm ở user_store.pin (thuần). Dùng bởi:
server_app/web_auth/routes (login), tools/add_web_user.py (CLI quản lý).
"""
from __future__ import annotations

import time

from user_store.pin import hash_pin, verify_pin
from user_store.schema import get_users_conn


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
    }


def add_user(username: str, pin: str, display_name: str = "", role: str = "staff", *, db_path: str | None = None) -> dict:
    """Tạo user mới. Raise ValueError nếu username trống/toàn số/PIN trống/đã tồn tại."""
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("username trống")
    if username.isdigit():
        # username toàn số sẽ bị các consumer (resolve_name, task actor) nhầm là
        # Telegram user id — cấm từ gốc
        raise ValueError("username không được toàn số — thêm chữ cái")
    if not pin:
        raise ValueError("PIN trống")
    conn = get_users_conn(db_path)
    try:
        try:
            conn.execute(
                "INSERT INTO web_users (username, pin_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, hash_pin(pin), display_name or username, role, int(time.time())),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise ValueError(f"username '{username}' đã tồn tại") from exc
            raise
        row = conn.execute("SELECT * FROM web_users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row)


def get_user(username: str, *, db_path: str | None = None) -> dict | None:
    conn = get_users_conn(db_path)
    try:
        row = conn.execute("SELECT * FROM web_users WHERE username = ?", ((username or "").strip().lower(),)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_users(*, db_path: str | None = None) -> list[dict]:
    conn = get_users_conn(db_path)
    try:
        rows = conn.execute("SELECT * FROM web_users ORDER BY username").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def set_disabled(username: str, disabled: bool, *, db_path: str | None = None) -> bool:
    """Khoá/mở user. Trả True nếu có user bị đổi."""
    conn = get_users_conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE web_users SET disabled = ? WHERE username = ?",
            (1 if disabled else 0, (username or "").strip().lower()),
        )
        return cur.rowcount > 0
    finally:
        conn.close()


def verify_login(username: str, pin: str, *, db_path: str | None = None) -> dict | None:
    """Đúng username + PIN + chưa bị khoá → dict user; sai → None."""
    conn = get_users_conn(db_path)
    try:
        row = conn.execute("SELECT * FROM web_users WHERE username = ?", ((username or "").strip().lower(),)).fetchone()
    finally:
        conn.close()
    if row is None or row["disabled"]:
        return None
    if not verify_pin(pin or "", row["pin_hash"]):
        return None
    return _row_to_dict(row)
