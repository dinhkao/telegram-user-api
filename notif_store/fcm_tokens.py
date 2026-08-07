"""Bảng `fcm_tokens` (app.db) — token thiết bị FCM đăng ký theo USER.

Có bảng này thì push FCM gửi được THEO TỪNG MÁY thay vì bắn topic chung, nhờ đó
lọc bỏ user vai trò bó hẹp (chat_luong) và user đã bị khoá khỏi mọi thông báo.

1 row = 1 token (1 lần cài app trên 1 máy). Token là PRIMARY KEY: máy đó đổi người
đăng nhập thì row cũ được ghi đè username, không sinh row rác.

Connection qua utils.db. Ghi: server_app/fcm_routes.py (POST /api/fcm/register).
Đọc/dọn: server_app/fcm.py (gửi push + xoá token chết).
"""
from __future__ import annotations

from datetime import UTC, datetime

from utils.db import transaction

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS fcm_tokens (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_fcm_tokens_user ON fcm_tokens(username)"

# DDL chạy 1 lần mỗi FILE DB mỗi process — như user_store.schema. Khoá theo ĐƯỜNG DẪN
# (không phải id(conn): id bị tái dùng sau GC → DB mới có thể trượt DDL, và test dùng
# nhiều file tạm khác nhau).
_ensured: set[str] = set()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _db_key(conn) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2] if row else "")
    except Exception:
        return ""


def ensure_table(conn) -> None:
    """Tạo bảng + index nếu chưa có (idempotent, 1 lần mỗi file DB mỗi process)."""
    key = _db_key(conn)
    if key and key in _ensured:
        return
    conn.execute(_CREATE_SQL)
    conn.execute(_INDEX_SQL)
    if key:
        _ensured.add(key)


def register_token(conn, token: str, username: str) -> None:
    """Upsert token → username. Token đã có (máy đổi người đăng nhập) thì đổi
    username + updated_at, không tạo row thứ hai."""
    ensure_table(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO fcm_tokens (token, username, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET username = excluded.username, "
            "updated_at = excluded.updated_at",
            (token, username, _now_iso()),
        )


def eligible_tokens(conn, exclude_roles: tuple[str, ...] = ("chat_luong",)) -> list[str]:
    """Token ĐƯỢC nhận push: JOIN web_users nên token của username không còn trong
    bảng user tự rụng; loại user bị khoá (disabled) và vai trò trong exclude_roles."""
    ensure_table(conn)
    roles = tuple(exclude_roles or ())
    sql = (
        "SELECT t.token FROM fcm_tokens t "
        "JOIN web_users u ON u.username = t.username "
        "WHERE COALESCE(u.disabled, 0) = 0"
    )
    params: tuple = ()
    if roles:
        sql += " AND COALESCE(u.role, '') NOT IN (%s)" % ",".join("?" * len(roles))
        params = roles
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def delete_tokens(conn, tokens) -> int:
    """Xoá token chết (FCM báo UNREGISTERED/INVALID_ARGUMENT). Trả số row đã xoá."""
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return 0
    ensure_table(conn)
    with transaction(conn):
        cur = conn.execute(
            "DELETE FROM fcm_tokens WHERE token IN (%s)" % ",".join("?" * len(toks)),
            tuple(toks),
        )
    return cur.rowcount or 0
