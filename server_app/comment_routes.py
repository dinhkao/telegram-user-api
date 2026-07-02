"""HTTP handlers bình luận web trên đơn — GET/POST /api/order/{thread_id}/comments.

Người bình luận = request["web_user"] (web_auth middleware); chưa đăng nhập thì
nhận từ body["user"] (giai đoạn chưa bật chặn). DB-only — không gửi Telegram.
Connects to: comment_store. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from comment_store import add_comment, list_comments


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return None


async def comments_list_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    comments = await asyncio.to_thread(list_comments, thread_id)
    return web.json_response({"ok": True, "comments": comments})


async def comments_add_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    from server_app.order_api_common import apply_web_actor
    apply_web_actor(request, body, key="user")
    username = str(body.get("user") or "").strip() or "?"
    try:
        comment = await asyncio.to_thread(add_comment, thread_id, username, str(body.get("text") or ""))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    # Đẩy realtime để trang chi tiết đang mở tải lại bình luận (chạy nền)
    from server_app.realtime import emit_order_changed
    emit_order_changed(thread_id)
    # Push FCM cho app (best-effort, tắt nếu FCM_ENABLED=false)
    from server_app.fcm import notify_bg
    notify_bg("💬 Bình luận mới", f"{username}: {comment['text'][:100]}", {"thread_id": str(thread_id), "type": "comment"})
    return web.json_response({"ok": True, "comment": comment})
