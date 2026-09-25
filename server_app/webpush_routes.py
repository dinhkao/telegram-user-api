"""API Web Push (iPhone PWA / trình duyệt) — đăng ký máy theo USER đang đăng nhập.

GET  /api/webpush/key          → khoá công khai VAPID (client subscribe)
POST /api/webpush/subscribe    {subscription:{endpoint, keys:{p256dh, auth}}}
POST /api/webpush/unsubscribe  {endpoint}   (chỉ gỡ đăng ký CỦA MÌNH)
POST /api/webpush/test         gửi thử 1 push CHỈ tới các máy của chính người bấm
Endpoint chỉ nhận host dịch vụ push thật (webpush.endpoint_allowed — chặn SSRF).
subscribe/key nằm trong _NO_AUDIT (gọi mỗi lần mở app). Nối: notif_store.webpush_subs,
server_app.webpush. Đăng ký route ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection


def _user(request) -> str | None:
    return request.get("web_user")


async def webpush_key_handler(request: web.Request):
    from server_app import webpush
    if not webpush.enabled():
        return web.json_response({"ok": True, "enabled": False, "key": ""})
    return web.json_response({"ok": True, "enabled": True, "key": await asyncio.to_thread(webpush.public_key)})


async def webpush_subscribe_handler(request: web.Request):
    user = _user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chưa đăng nhập"}, status=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    sub = (body or {}).get("subscription") or {}
    endpoint = str(sub.get("endpoint") or "").strip()
    keys = sub.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    from server_app.webpush import endpoint_allowed
    if not endpoint or len(endpoint) > 1000 or not endpoint_allowed(endpoint) \
            or not (0 < len(p256dh) <= 200) or not (0 < len(auth) <= 100):
        return web.json_response({"ok": False, "error": "Đăng ký thông báo không hợp lệ"}, status=400)

    def _save():
        from notif_store.webpush_subs import register_sub
        conn = get_connection()
        try:
            register_sub(conn, endpoint=endpoint, username=user, p256dh=p256dh, auth=auth,
                         user_agent=request.headers.get("User-Agent", ""))
        finally:
            conn.close()
    await asyncio.to_thread(_save)
    return web.json_response({"ok": True})


async def webpush_unsubscribe_handler(request: web.Request):
    user = _user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chưa đăng nhập"}, status=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    endpoint = str((body or {}).get("endpoint") or "")

    def _del():
        from notif_store.webpush_subs import delete_subs, subs_of_user
        conn = get_connection()
        try:
            return delete_subs(conn, [endpoint]) if endpoint in subs_of_user(conn, user) else 0
        finally:
            conn.close()
    return web.json_response({"ok": True, "removed": await asyncio.to_thread(_del)})


async def webpush_test_handler(request: web.Request):
    """Gửi thử CHỈ tới máy của chính mình (không ghi chuông thông báo, không làm phiền ai)."""
    user = _user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chưa đăng nhập"}, status=401)

    def _run():
        from notif_store.webpush_subs import subs_of_user
        from server_app.webpush import send_once
        conn = get_connection()
        try:
            eps = subs_of_user(conn, user)
        finally:
            conn.close()
        if not eps:
            return {"ok": False, "error": "Máy này chưa bật thông báo"}
        r = send_once("🔔 Thử thông báo", "Bạn sẽ nhận thông báo đơn hàng trên máy này.", {"route": "#/orders"}, eps)
        return {"ok": bool(r["ok_users"]), "sent": len(r["ok_users"]),
                "error": None if r["ok_users"] else "Gửi chưa được — thử lại sau"}
    return web.json_response(await asyncio.to_thread(_run))
