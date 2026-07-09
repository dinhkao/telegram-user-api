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


def rename_user(old_username: str, new_username: str, *, db_path: str | None = None) -> dict:
    """Đổi username AN TOÀN — cascade cùng 1 transaction sang mọi bảng dùng
    username làm KHOÁ THAM CHIẾU: web_tasks (assignee/done_by/created_by),
    web_comments/entity_comments/order_image_comments (username). Các cột *_by
    kiểu LOG/audit (actor snapshot, lẫn tên hiển thị/IP) CỐ Ý giữ nguyên — đó là
    sự thật tại thời điểm đó. Token đăng nhập cũ hết hiệu lực (chứa username cũ)
    → user đăng nhập lại. Trả {counts theo bảng}."""
    old = (old_username or "").strip().lower()
    new = (new_username or "").strip().lower()
    if not old or not new:
        raise ValueError("username trống")
    if new == old:
        raise ValueError("username mới trùng username cũ")
    if new.isdigit():
        raise ValueError("username không được toàn số — thêm chữ cái")
    conn = get_users_conn(db_path)
    try:
        if not conn.execute("SELECT 1 FROM web_users WHERE username = ?", (old,)).fetchone():
            raise ValueError(f"username '{old}' không tồn tại")
        if conn.execute("SELECT 1 FROM web_users WHERE username = ?", (new,)).fetchone():
            raise ValueError(f"username '{new}' đã tồn tại")
        counts: dict[str, int] = {}
        cascades = [
            ("web_users", "UPDATE web_users SET username = ? WHERE username = ?"),
            ("web_tasks.assignee", "UPDATE web_tasks SET assignee = ? WHERE assignee = ?"),
            ("web_tasks.done_by", "UPDATE web_tasks SET done_by = ? WHERE done_by = ?"),
            ("web_tasks.created_by", "UPDATE web_tasks SET created_by = ? WHERE created_by = ?"),
            ("web_comments", "UPDATE web_comments SET username = ? WHERE username = ?"),
            ("entity_comments", "UPDATE entity_comments SET username = ? WHERE username = ?"),
            ("order_image_comments", "UPDATE order_image_comments SET username = ? WHERE username = ?"),
        ]
        conn.execute("BEGIN IMMEDIATE")
        try:
            for label, sql in cascades:
                try:
                    cur = conn.execute(sql, (new, old))
                    counts[label] = cur.rowcount
                except Exception:  # noqa: BLE001 — bảng chưa tạo (DB test/tối giản)
                    counts[label] = 0
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return counts


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


def set_pin(username: str, pin: str, *, db_path: str | None = None) -> bool:
    """Đổi PIN. Trả True nếu có user bị đổi."""
    if not pin:
        raise ValueError("PIN trống")
    conn = get_users_conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE web_users SET pin_hash = ? WHERE username = ?",
            (hash_pin(pin), (username or "").strip().lower()),
        )
        return cur.rowcount > 0
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


# Vai trò: admin (toàn quyền) ⊃ van_phong (văn phòng: nhận tiền + tạo thanh toán) ⊃
# staff (nhân viên). "Văn phòng" = admin hoặc van_phong.
ROLES = ("admin", "van_phong", "staff")
OFFICE_ROLES = ("admin", "van_phong")


def is_office(role: str | None) -> bool:
    """True nếu role thuộc nhóm 'văn phòng' (admin/van_phong)."""
    return (role or "") in OFFICE_ROLES


def set_role(username: str, role: str, *, db_path: str | None = None) -> bool:
    """Đổi vai trò user. role ∈ ROLES. Trả True nếu có user bị đổi."""
    if role not in ROLES:
        raise ValueError(f"role không hợp lệ: {role} (phải là {ROLES})")
    conn = get_users_conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE web_users SET role = ? WHERE username = ?",
            (role, (username or "").strip().lower()),
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
