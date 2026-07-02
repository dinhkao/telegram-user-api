"""aiohttp middleware web_auth — gắn request["web_user"] từ token; chặn /api/* khi bật.

Luôn giải token nếu client gửi (Authorization: Bearer … hoặc ?token=) → attribution
chạy cả khi chưa bật chặn. Enforcement chỉ khi WEB_AUTH_ENABLED=true.
Miễn chặn: /api/auth/login, /api/tg/* (đã có X-API-Key riêng), OPTIONS, và mọi
đường dẫn ngoài /api/ (pages/static/ws — gate ở phase sau).
Dùng bởi: server_app/app_factory. Logic quyết định thuần: is_exempt/extract_token.
"""
from __future__ import annotations

import os
import time

from aiohttp import web

from server_app.web_auth.secret import get_web_auth_secret
from server_app.web_auth.token import verify_token

WEB_AUTH_ENABLED = os.getenv("WEB_AUTH_ENABLED", "false").strip().lower() in ("1", "true", "yes")

_EXEMPT_EXACT = {"/api/auth/login", "/api/auth/me"}
_EXEMPT_PREFIXES = ("/api/tg/",)


def is_exempt(method: str, path: str) -> bool:
    """Request này có được miễn kiểm token không (logic thuần, unit-test)."""
    if method == "OPTIONS":
        return True
    if not path.startswith("/api/"):
        return True
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def extract_token(headers, query) -> str:
    """Lấy token từ header Bearer, không có thì ?token= (cho WebSocket)."""
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return (query.get("token") or "").strip()


@web.middleware
async def web_auth_middleware(request: web.Request, handler):
    token = extract_token(request.headers, request.query)
    if token:
        username = verify_token(get_web_auth_secret(), token, now=int(time.time()))
        if username:
            request["web_user"] = username
    if WEB_AUTH_ENABLED and not is_exempt(request.method, request.path) and "web_user" not in request:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    return await handler(request)
