"""CORS middleware — cho WebView APK (origin https://appassets.androidplatform.net)
và dev (localhost:5174) gọi được /api/* cross-origin.

Allow-Origin: * an toàn ở đây vì auth qua header Authorization (không cookie),
và server chỉ trong Tailscale. Preflight OPTIONS trả 204 ngay (route không cần
khai OPTIONS). Đăng ký ở server_app/app_factory (trước web_auth).
"""
from __future__ import annotations

from aiohttp import web

_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key",
    "Access-Control-Max-Age": "86400",
}


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_HEADERS)
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        exc.headers.extend(_HEADERS)
        raise
    response.headers.update(_HEADERS)
    return response
