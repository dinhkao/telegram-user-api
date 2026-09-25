"""Trung tâm thông báo — GHI 1 notification row + PUSH FCM + realtime từ MỘT chỗ,
để notification center trong app luôn khớp với push FCM.

push_bg(title, body, data): data giống payload FCM cũ ({thread_id, type, comment_id/
image_id}). Thông báo KHÔNG thuộc đơn hàng đặt data['route'] = hash webapp
('#/kho-dau/phieu/12') → NotifCenter mở thẳng route đó.
Dùng thay server_app.fcm.notify_bg ở các điểm sự kiện (comment/ảnh…). Push đi qua
HÀNG ĐỢI BỀN server_app.push_outbox (gửi bù khi lỗi mạng/restart).
Đọc: GET /api/notifications (notifications_list_handler). Kết nối: notif_store,
server_app.fcm, server_app.realtime.
"""
from __future__ import annotations

import asyncio
import logging
import os

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


def _order_peek(conn, thread_id: int | None) -> str:
    """Dòng đầu nội dung đơn (≤80 ký tự) để thông báo ghi rõ 'vào đơn <text>'."""
    if not thread_id:
        return ""
    try:
        from order_store.serialization import get_order_by_thread_id
        o = get_order_by_thread_id(conn, thread_id)
        if not o:
            return ""
        txt = (o.get("text") or o.get("text_raw") or "").strip()
        return txt.split("\n", 1)[0].strip()[:80] if txt else ""
    except Exception:  # noqa: BLE001
        return ""


def _fcm_image_url(thread_id: int | None, image_id: int | None) -> str | None:
    """URL tuyệt đối tới ảnh đơn cho FCM big-picture (Android). Cần WEBAPP_URL +
    máy nhận truy cập được (Tailscale). Không có config → None (bỏ ảnh, push thường)."""
    base = os.getenv("WEBAPP_URL", "").rstrip("/")
    if not base or not thread_id or not image_id:
        return None
    return f"{base}/api/order/{thread_id}/images/{image_id}/file?size=full"


async def _push(title: str, body: str, data: dict | None) -> None:
    focus = _focus(data)
    thread_id = None
    try:
        thread_id = int(data["thread_id"]) if data and data.get("thread_id") else None
    except (ValueError, TypeError):
        thread_id = None
    ntype = (data or {}).get("type") or "info"
    route = str((data or {}).get("route") or "") or None
    image_id = None
    try:
        image_id = int(data["image_id"]) if data and data.get("image_id") else None
    except (ValueError, TypeError):
        image_id = None

    def _w():
        conn = get_connection()
        try:
            # Thông báo ảnh: ghi rõ đơn nào — nối dòng đầu nội dung đơn vào body
            fb = body
            if ntype == "image":
                peek = _order_peek(conn, thread_id)
                if peek:
                    fb = f"{body} {peek}"
            from notif_store import create_notif_table, add_notification, prune_old
            from notif_store.push_state import mark_pending
            from server_app.push_outbox import first_next_at
            create_notif_table(conn)
            row = add_notification(conn, type=ntype, title=title, body=fb,
                                   thread_id=thread_id, focus=focus, image_id=image_id,
                                   route=route)
            # Đưa vào HÀNG ĐỢI PUSH BỀN trước khi gửi → lỗi mạng/restart vẫn được gửi bù
            mark_pending(conn, row["id"], {"title": title, "body": fb, "data": data or {},
                                           "image_url": image_url, "tokens": None, "topic": True},
                         first_next_at())
            prune_old(conn)
            return row, fb
        finally:
            conn.close()

    image_url = _fcm_image_url(thread_id, image_id) if ntype == "image" else None
    try:
        row, final_body = await asyncio.to_thread(_w)
    except Exception as e:  # noqa: BLE001 — không ghi được DB → vẫn phải push (không có gửi bù)
        log.warning("Ghi notification lỗi: %s", e)
        from server_app.fcm import notify_bg
        notify_bg(title, body, data, image_url=image_url)
        return
    from server_app.realtime import emit_notif_added
    emit_notif_added(row)
    # Push FCM qua hàng đợi bền (tự bỏ qua nếu FCM_ENABLED=false). Ảnh → big-picture.
    from server_app.push_outbox import deliver
    await deliver(int(row["id"]))


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
