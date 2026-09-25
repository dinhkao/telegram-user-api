"""CRUD nhật ký thông báo (bảng notifications, app.db). IO thuần."""
from __future__ import annotations

from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def add_notification(conn, *, type: str, title: str, body: str,
                     thread_id: int | None = None, focus: str | None = None,
                     image_id: int | None = None, route: str | None = None,
                     audience: str | None = None) -> dict:
    """route = hash webapp cho thông báo KHÔNG thuộc đơn (vd '#/kho-dau/phieu/12').
    audience='office' → chỉ văn phòng thấy (danh sách/realtime/push)."""
    cur = conn.execute(
        "INSERT INTO notifications (type, title, body, thread_id, focus, image_id, route, audience, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (type, title, body, thread_id, focus, image_id, route, audience, _now_iso()),
    )
    conn.commit()
    return get_notification(conn, cur.lastrowid)


# Cột nội bộ hàng đợi push (chứa TOKEN máy) — không bao giờ trả ra API/realtime
_HIDDEN = ("push_payload", "push_next_at")


def _public(row) -> dict:
    d = dict(row)
    for k in _HIDDEN:
        d.pop(k, None)
    return d


def get_notification(conn, notif_id) -> dict | None:
    row = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
    return _public(row) if row else None


# Người KHÔNG phải văn phòng chỉ thấy thông báo audience NULL (không lộ trao đổi lương)
_PUBLIC_WHERE = " WHERE audience IS NULL"


def list_notifications(conn, *, limit=30, office: bool = True) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notifications" + ("" if office else _PUBLIC_WHERE) + " ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_public(r) for r in rows]


def latest_id(conn, office: bool = True) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM notifications" + ("" if office else _PUBLIC_WHERE)).fetchone()
    return int(row["m"]) if row else 0


def prune_old(conn, *, keep=500) -> int:
    """Giữ lại `keep` thông báo mới nhất, xoá phần cũ (chống phình bảng)."""
    cur = conn.execute(
        "DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT ?)",
        (keep,),
    )
    conn.commit()
    return cur.rowcount
