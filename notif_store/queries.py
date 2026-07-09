"""CRUD nhật ký thông báo (bảng notifications, app.db). IO thuần."""
from __future__ import annotations

from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def add_notification(conn, *, type: str, title: str, body: str,
                     thread_id: int | None = None, focus: str | None = None,
                     image_id: int | None = None) -> dict:
    cur = conn.execute(
        "INSERT INTO notifications (type, title, body, thread_id, focus, image_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (type, title, body, thread_id, focus, image_id, _now_iso()),
    )
    conn.commit()
    return get_notification(conn, cur.lastrowid)


def get_notification(conn, notif_id) -> dict | None:
    row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
    return dict(row) if row else None


def list_notifications(conn, *, limit=30) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def latest_id(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM notifications").fetchone()
    return int(row["m"]) if row else 0


def prune_old(conn, *, keep=500) -> int:
    """Giữ lại `keep` thông báo mới nhất, xoá phần cũ (chống phình bảng)."""
    cur = conn.execute(
        "DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT ?)",
        (keep,),
    )
    conn.commit()
    return cur.rowcount
