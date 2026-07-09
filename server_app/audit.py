from __future__ import annotations

import json
import re
import time

from aiohttp import web

from audit_log import async_log_event, new_request_id
from server_app import order_diff

# Endpoint TẠM (không phải ghi dữ liệu) — KHÔNG audit: nháp báo cáo (mỗi phím gõ),
# khoá/nhả, xem trước. Nếu ghi sẽ ngập "draft" trong lịch sử thao tác.
_NO_AUDIT = re.compile(r"/report/(draft|lock|unlock|parse)$")
_ORDER_PATH = re.compile(r"^/api/order/(-?\d+)")
_PRODUCTION_PATH = re.compile(r"^/api/production/(-?\d+)")
_MEDIA_PATH = re.compile(r"^/api/media/(production|box|return|task)/(-?\d+)")
_RETURN_PATH = re.compile(r"^/api/returns/(\d+)")
_INV_BOX_PATH = re.compile(r"^/api/inventory/box/(-?\d+)")


def _load_order_snapshot(thread_id):
    """Đọc blob đơn (readonly) để chụp trạng thái trước/sau 1 thao tác. Không được
    làm hỏng request nếu lỗi → trả None."""
    if thread_id is None:
        return None
    try:
        from order_db import _get_connection
        from order_store import get_order_by_thread_id
        conn = _get_connection()
        try:
            return get_order_by_thread_id(conn, int(thread_id))
        finally:
            conn.close()
    except Exception:
        return None


def _scope_entity(path: str, body_text: str | None):
    """(scope, entity_id) để gắn vào audit event → lịch sử thao tác theo đơn/phiếu/thùng.
    scope ∈ {order, production, box}. entity_id = thread_id (order/production) hoặc box_id."""
    m = _MEDIA_PATH.match(path)
    if m:
        return m.group(1), int(m.group(2))
    m = _RETURN_PATH.match(path)
    if m:
        return "return", int(m.group(1))
    m = _INV_BOX_PATH.match(path)
    if m:
        return "box", int(m.group(1))
    m = _PRODUCTION_PATH.match(path)
    if m:
        return "production", int(m.group(1))
    m = _ORDER_PATH.match(path)
    if m:
        return "order", int(m.group(1))
    if body_text:
        try:
            tid = json.loads(body_text).get("thread_id")
            if tid is not None:
                return "order", int(tid)
        except Exception:
            return None, None
    return None, None


@web.middleware
async def audit_middleware(request: web.Request, handler):
    request_id = new_request_id()
    request["request_id"] = request_id
    if _NO_AUDIT.search(request.path):   # endpoint tạm → chạy thẳng, không ghi audit
        return await handler(request)
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
    # Chụp trạng thái đơn TRƯỚC khi handler chạy (chỉ với POST sửa đơn) để so cũ→mới
    scope, entity_id = _scope_entity(request.path, body_text)
    is_mut = scope == "order" and order_diff.is_order_mutation(request.method, request.path)
    before = _load_order_snapshot(entity_id) if is_mut else None
    try:
        response = await handler(request)
        changes = None
        if is_mut and 200 <= response.status < 300:
            after = _load_order_snapshot(entity_id)
            changes = order_diff.diff_changes(before, after)
        await _log_http(request, request_id, start, response.status, body_text, changes=changes)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        await _log_http(request, request_id, start, None, body_text, error=exc)
        raise


async def _log_http(request, request_id, start, status, body_text, error=None, changes=None):
    web_user = request.get("web_user")   # do web_auth middleware gắn (nếu có token)
    scope, entity_id = _scope_entity(request.path, body_text)
    await async_log_event(
        "http.request", request_id=request_id,
        actor_type="web_user" if web_user else "http_client",
        actor_id=web_user or request.remote,
        scope=scope, thread_id=entity_id,
        direction="in", source=f"{request.method} {request.path}",
        payload={"method": request.method, "path": request.path, "query": dict(request.query), "headers": dict(request.headers), "body": body_text if body_text is not None else "<multipart-or-empty>", "changes": changes or []},
        result=None if status is None else {"status": status}, error=error, duration_ms=(time.perf_counter() - start) * 1000,
    )
