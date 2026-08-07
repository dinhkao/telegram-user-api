"""POST /api/fcm/register — máy Android đăng ký token FCM của mình theo USER.

APK gọi mỗi lần mở app (cầu JS window.AndroidApp.fcmToken). Nhờ bảng
`fcm_tokens` mà push gửi được theo từng máy thay vì topic chung → lọc bỏ vai trò
bó hẹp (chat_luong) và user bị khoá. Kết nối: notif_store.fcm_tokens, utils.db.
Đăng ký route ở server_app/app_factory.py; nằm trong _NO_AUDIT (mỗi lần mở app).
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from notif_store.fcm_tokens import register_token
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
