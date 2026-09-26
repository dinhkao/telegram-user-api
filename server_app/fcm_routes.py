"""POST /api/fcm/register — máy Android đăng ký token FCM của mình theo USER.
POST /api/fcm/unregister — ĐĂNG XUẤT: gỡ token của máy này khỏi user đang đăng nhập.

APK gọi mỗi lần mở app (cầu JS window.AndroidApp.fcmToken). Nhờ bảng
`fcm_tokens` mà push gửi được theo từng máy thay vì topic chung → lọc bỏ vai trò
bó hẹp (chat_luong) và user bị khoá. Kết nối: notif_store.fcm_tokens, utils.db.
Đăng ký route ở server_app/app_factory.py; cả 2 nằm trong _NO_AUDIT (body chứa token).
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from notif_store.fcm_tokens import register_token, unregister_token
from utils.db import get_connection

log = logging.getLogger("server")

_MAX_TOKEN_LEN = 4096


def _save(token: str, username: str) -> None:
    conn = get_connection()
    try:
        register_token(conn, token, username)
    finally:
        conn.close()


async def fcm_register_handler(request: web.Request) -> web.Response:
    username = request.get("web_user")
    if not username:
        return web.json_response({"ok": False, "error": "Chưa đăng nhập"}, status=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    token = str((body or {}).get("token") or "").strip()
    if not token or len(token) > _MAX_TOKEN_LEN:
        return web.json_response({"ok": False, "error": "Token không hợp lệ"}, status=400)
    await asyncio.to_thread(_save, token, username)
    return web.json_response({"ok": True})


async def fcm_unregister_handler(request: web.Request) -> web.Response:
    """Gọi TRƯỚC khi client xoá đăng nhập: máy thôi đứng tên user này → hết nhận push."""
    username = request.get("web_user")
    if not username:
        return web.json_response({"ok": False, "error": "Chưa đăng nhập"}, status=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    token = str((body or {}).get("token") or "").strip()
    if not token or len(token) > _MAX_TOKEN_LEN:
        return web.json_response({"ok": False, "error": "Token không hợp lệ"}, status=400)

    def _del() -> int:
        conn = get_connection()
        try:
            return unregister_token(conn, token, username)
        finally:
            conn.close()
    removed = await asyncio.to_thread(_del)
    log.info("FCM: %s đăng xuất — gỡ %d token của máy", username, removed)
    return web.json_response({"ok": True, "removed": removed})
