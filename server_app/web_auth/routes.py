"""HTTP handlers đăng nhập web app — POST /api/auth/login, GET /api/auth/me.

Login: username + PIN (user_store.verify_login) → token HMAC (web_auth.token),
sai thì chờ 0.5s (hãm brute-force PIN ngắn). /api/auth/me: cho frontend biết
đang đăng nhập là ai + server có bật chặn không. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

from server_app.config import WEB_AUTH_ENABLED, WEB_AUTH_TOKEN_TTL
from server_app.web_auth.secret import get_web_auth_secret
from server_app.web_auth.token import issue_token
from user_store import get_user, verify_login


async def login_handler(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    username = str(data.get("username", ""))
    pin = str(data.get("pin", ""))
    user = await asyncio.to_thread(verify_login, username, pin)
    if user is None:
        await asyncio.sleep(0.5)
        return web.json_response({"ok": False, "error": "Sai tên đăng nhập hoặc PIN"}, status=401)
    token = issue_token(
        get_web_auth_secret(), user["username"], ttl_seconds=WEB_AUTH_TOKEN_TTL, now=int(time.time())
    )
    return web.json_response({
        "ok": True,
        "token": token,
        "user": {"username": user["username"], "display_name": user["display_name"], "role": user["role"]},
    })


async def me_handler(request: web.Request):
    username = request.get("web_user")
    if not username:
        return web.json_response({"ok": True, "auth_enabled": WEB_AUTH_ENABLED, "user": None})
    user = await asyncio.to_thread(get_user, username)
    return web.json_response({
        "ok": True,
        "auth_enabled": WEB_AUTH_ENABLED,
        "user": None if user is None else {
            "username": user["username"], "display_name": user["display_name"], "role": user["role"],
        },
    })
