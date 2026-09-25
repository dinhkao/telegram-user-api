"""Trạng thái PUSH của từng thông báo (cột push_* bảng notifications) — hàng đợi bền để
push không bao giờ rơi mất vì lỗi mạng tới FCM hay server khởi động lại giữa chừng.

push_state: 'pending' (mới tạo, đang gửi lần đầu) · 'retry' (còn máy chưa nhận / lỗi
mạng — chờ gửi bù) · 'sent' (mọi máy đủ điều kiện đã nhận) · 'failed' (hết lượt thử)
· 'disabled' (FCM tắt). push_payload = JSON {title, body, data, image_url, tokens: null
(= mọi máy) | [token CÒN THIẾU], topic: còn phải gửi topic dự phòng?}. IO thuần; luật
chọn trạng thái ở server_app.push_outbox. Nối: bảng notifications (schema.py)."""
from __future__ import annotations

import json


def mark_pending(conn, notif_id: int, payload: dict, next_at: int) -> None:
    conn.execute(
        "UPDATE notifications SET push_state='pending', push_attempts=0, push_payload=?, push_next_at=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), int(next_at), int(notif_id)),
    )
    conn.commit()


def load(conn, notif_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, push_state, push_attempts, push_payload FROM notifications WHERE id=?", (int(notif_id),)
    ).fetchone()
    if not row or not row[3]:
        return None
    try:
        payload = json.loads(row[3])
    except (TypeError, ValueError):
        return None
    return {"id": row[0], "state": row[1], "attempts": int(row[2] or 0), "payload": payload}


def save_attempt(conn, notif_id: int, *, state: str, attempts: int, payload: dict,
                 next_at: int | None, result: str) -> None:
    conn.execute(
        "UPDATE notifications SET push_state=?, push_attempts=?, push_payload=?, push_next_at=?, push_result=? WHERE id=?",
        (state, int(attempts), json.dumps(payload, ensure_ascii=False), next_at, result[:1000], int(notif_id)),
    )
    conn.commit()


def due_ids(conn, now: int, since_iso: str, limit: int = 20) -> list[int]:
    """Thông báo cần gửi bù: đang chờ/cần thử lại, tới hạn, tạo sau `since_iso`."""
    rows = conn.execute(
        "SELECT id FROM notifications WHERE push_state IN ('pending','retry') AND push_next_at <= ? "
        "AND created_at >= ? ORDER BY id LIMIT ?",
        (int(now), since_iso, int(limit)),
    ).fetchall()
    return [int(r[0]) for r in rows]


def expire_old(conn, since_iso: str) -> int:
    """Push treo quá cửa sổ gửi bù → 'failed' (tin cũ gửi muộn hàng giờ là vô nghĩa)."""
    cur = conn.execute(
        "UPDATE notifications SET push_state='failed', push_result=COALESCE(push_result,'') || ' | quá hạn gửi bù' "
        "WHERE push_state IN ('pending','retry') AND created_at < ?",
        (since_iso,),
    )
    conn.commit()
    return cur.rowcount or 0
