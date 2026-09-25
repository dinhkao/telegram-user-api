"""Bảng `web_push_subs` (app.db) — đăng ký WEB PUSH theo USER (iPhone PWA / trình duyệt).

1 row = 1 subscription (1 trình duyệt/1 app PWA trên 1 máy), khoá `endpoint` (URL của
dịch vụ push: web.push.apple.com, fcm.googleapis.com…). Máy đổi người đăng nhập → ghi đè
username, không sinh row rác. Chọn người nhận GIỐNG hệt fcm_tokens: bỏ vai trò bó hẹp
(chat_luong) + user bị khoá; audience='office' chỉ admin/van_phong.
Ghi: server_app/webpush_routes.py · Đọc/dọn: server_app/webpush.py. Connection qua utils.db.
"""
from __future__ import annotations

from datetime import UTC, datetime

from utils.db import transaction

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS web_push_subs (
    endpoint   TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    user_agent TEXT,
    updated_at TEXT NOT NULL
)
"""
_ensured: set[str] = set()


def _db_key(conn) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2] if row else "")
    except Exception:  # noqa: BLE001
        return ""


def ensure_table(conn) -> None:
    key = _db_key(conn)
    if key and key in _ensured:
        return
    conn.execute(_CREATE_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_web_push_user ON web_push_subs(username)")
    if key:
        _ensured.add(key)


def register_sub(conn, *, endpoint: str, username: str, p256dh: str, auth: str, user_agent: str = "") -> None:
    ensure_table(conn)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with transaction(conn):
        conn.execute(
            "INSERT INTO web_push_subs (endpoint, username, p256dh, auth, user_agent, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(endpoint) DO UPDATE SET username=excluded.username, p256dh=excluded.p256dh, "
            "auth=excluded.auth, user_agent=excluded.user_agent, updated_at=excluded.updated_at",
            (endpoint, username, p256dh, auth, (user_agent or "")[:300], now),
        )


def delete_subs(conn, endpoints) -> int:
    eps = [e for e in (endpoints or []) if e]
    if not eps:
        return 0
    ensure_table(conn)
    with transaction(conn):
        cur = conn.execute("DELETE FROM web_push_subs WHERE endpoint IN (%s)" % ",".join("?" * len(eps)), tuple(eps))
    return cur.rowcount or 0


def eligible_subs(conn, *, exclude_roles=("chat_luong",), only_roles=None) -> list[dict]:
    """[{endpoint, username, p256dh, auth}] ĐƯỢC nhận push (JOIN web_users: bỏ user khoá,
    vai trò bị loại; only_roles → chỉ các vai trò đó)."""
    ensure_table(conn)
    sql = ("SELECT s.endpoint, s.username, s.p256dh, s.auth FROM web_push_subs s "
           "JOIN web_users u ON u.username = s.username WHERE COALESCE(u.disabled, 0) = 0")
    params: list = []
    if exclude_roles:
        sql += " AND COALESCE(u.role,'') NOT IN (%s)" % ",".join("?" * len(exclude_roles))
        params += list(exclude_roles)
    if only_roles:
        sql += " AND COALESCE(u.role,'') IN (%s)" % ",".join("?" * len(only_roles))
        params += list(only_roles)
    return [{"endpoint": r[0], "username": r[1], "p256dh": r[2], "auth": r[3]}
            for r in conn.execute(sql, tuple(params)).fetchall()]


def subs_of_user(conn, username: str) -> list[str]:
    ensure_table(conn)
    return [r[0] for r in conn.execute("SELECT endpoint FROM web_push_subs WHERE username=?", (username,)).fetchall()]
