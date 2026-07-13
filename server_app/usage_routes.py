"""HTTP thống kê sử dụng webapp — POST /api/usage/batch (user đăng nhập gửi đếm
gộp mỗi 20s, nằm trong _NO_AUDIT), GET /api/usage/stats (admin xem #/usage).

Nối: usage_store, server_app.order_api_common (is_admin_request). User lấy từ
request["web_user"] (web_auth middleware gắn từ token, không tin body).
"""
from __future__ import annotations

from aiohttp import web

import usage_store
from server_app.order_api_common import is_admin_request


async def usage_batch_handler(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body không hợp lệ"}, status=400)
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        return web.json_response({"ok": False, "error": "thiếu events"}, status=400)
    username = request.get("web_user") or "?"
    saved = usage_store.record_batch(username, events)
    return web.json_response({"ok": True, "saved": saved})


async def usage_stats_handler(request: web.Request) -> web.Response:
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin xem được thống kê"}, status=403)
    try:
        days = int(request.query.get("days") or 30)
    except ValueError:
        days = 30
    username = (request.query.get("user") or "").strip() or None
    return web.json_response({"ok": True, **usage_store.stats(days, username=username)})
