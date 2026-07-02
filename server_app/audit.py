from __future__ import annotations

import time

from aiohttp import web

from audit_log import async_log_event, new_request_id


@web.middleware
async def audit_middleware(request: web.Request, handler):
    request_id = new_request_id()
    request["request_id"] = request_id
    start = time.perf_counter()
    body_text = None
    if request.path == "/api/auth/login":
        # body chứa PIN cleartext — không được ghi vào audit DB
        body_text = "<login body redacted>"
    elif request.can_read_body and not (request.content_type or "").startswith("multipart/"):
        try:
            body_text = await request.text()
        except Exception as exc:
            body_text = f"<body read failed: {type(exc).__name__}: {exc}>"
    try:
        response = await handler(request)
        await _log_http(request, request_id, start, response.status, body_text)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        await _log_http(request, request_id, start, None, body_text, error=exc)
        raise


async def _log_http(request, request_id, start, status, body_text, error=None):
    await async_log_event(
        "http.request", request_id=request_id, actor_type="http_client", actor_id=request.remote,
        direction="in", source=f"{request.method} {request.path}",
        payload={"method": request.method, "path": request.path, "query": dict(request.query), "headers": dict(request.headers), "body": body_text if body_text is not None else "<multipart-or-empty>"},
        result=None if status is None else {"status": status}, error=error, duration_ms=(time.perf_counter() - start) * 1000,
    )
