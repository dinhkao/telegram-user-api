"""CORS middleware — CHỈ cho origin trong allowlist (WEB_CORS_ORIGINS: WebView APK
appassets.androidplatform.net + dev localhost:5174) gọi /api/* cross-origin.

Origin lạ không nhận header CORS → trình duyệt tự chặn đọc/preflight (giữ nguyên
rào same-origin cho phần API chưa bật auth). Preflight OPTIONS từ origin hợp lệ
trả 204 ngay. Lỗi không phải HTTPException → trả 500 JSON kèm header CORS để
client web đọc được lỗi thay vì "network error" mù.
Đăng ký ở server_app/app_factory (ngoài cùng).
"""
from __future__ import annotations

import logging

from aiohttp import web

from server_app.config import WEB_CORS_ORIGINS

log = logging.getLogger("server")

_ALLOW = {
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key",
    "Access-Control-Max-Age": "86400",
}


def cors_headers(origin: str) -> dict:
    """Header CORS cho origin này — rỗng nếu không nằm trong allowlist (logic thuần)."""
    if origin in WEB_CORS_ORIGINS:
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin", **_ALLOW}
    return {}


@web.middleware
async def cors_middleware(request: web.Request, handler):
    headers = cors_headers(request.headers.get("Origin", ""))
    if request.method == "OPTIONS" and headers:
        return web.Response(status=204, headers=headers)
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        exc.headers.extend(headers)
        raise
    except Exception:
        log.exception("unhandled error: %s %s", request.method, request.path)
        return web.json_response({"ok": False, "error": "internal server error"}, status=500, headers=headers)
    if headers and not isinstance(response, web.WebSocketResponse):
        response.headers.update(headers)
    return response
