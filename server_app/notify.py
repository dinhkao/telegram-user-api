"""Trung tâm thông báo — GHI 1 notification row + PUSH FCM + realtime từ MỘT chỗ,
để notification center trong app luôn khớp với push FCM.

push_bg(title, body, data): data giống payload FCM cũ ({thread_id, type, comment_id/
image_id}). Dùng thay server_app.fcm.notify_bg ở các điểm sự kiện (comment/ảnh…).
Đọc: GET /api/notifications (notifications_list_handler). Kết nối: notif_store,
server_app.fcm, server_app.realtime.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from utils.db import get_connection

log = logging.getLogger("server")


def _focus(data: dict | None) -> str | None:
    """'<type>:<id>' cho deep-link OrderDetail (?focus=comment:123)."""
    if not data:
        return None
    t = data.get("type")
    for k in ("comment_id", "image_id"):
        if data.get(k):
            return f"{t}:{data[k]}"
    return None


async def _push(title: str, body: str, data: dict | None) -> None:
    focus = _focus(data)
    thread_id = None
    try:
        thread_id = int(data["thread_id"]) if data and data.get("thread_id") else None
    except (ValueError, TypeError):
        thread_id = None
    ntype = (data or {}).get("type") or "info"

    def _w():
        conn = get_connection()
        try:
            from notif_store import create_notif_table, add_notification, prune_old
            create_notif_table(conn)
            row = add_notification(conn, type=ntype, title=title, body=body,
                                   thread_id=thread_id, focus=focus)
            prune_old(conn)
            return row
        finally:
            conn.close()

    try:
        row = await asyncio.to_thread(_w)
        from server_app.realtime import emit_notif_added
        emit_notif_added(row)
    except Exception as e:  # noqa: BLE001
        log.warning("Ghi notification lỗi: %s", e)
    # Push FCM (best-effort, tự bỏ qua nếu FCM_ENABLED=false)
    from server_app.fcm import notify_bg
    notify_bg(title, body, data)


def push_bg(title: str, body: str, data: dict | None = None) -> None:
    """Lên lịch ghi + push chạy nền (không chặn handler gọi)."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("notify.push", _push(title, body, data))


async def notifications_list_handler(request: web.Request):
    try:
        limit = max(1, min(100, int(request.query.get("limit", "30"))))
    except (ValueError, TypeError):
        limit = 30

    def _run():
        conn = get_connection()
        try:
            from notif_store import create_notif_table, list_notifications, latest_id
            create_notif_table(conn)
            return list_notifications(conn, limit=limit), latest_id(conn)
        finally:
            conn.close()

    rows, latest = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "notifications": rows, "latest_id": latest})
