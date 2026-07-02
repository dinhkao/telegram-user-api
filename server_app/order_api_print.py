from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id
from print_service import execute_print_giao

from server_app import state
from server_app.config import ORDER_GROUP_ID
from server_app.order_api_common import apply_web_actor, resolve_name
from server_app.tasks import spawn_tracked
from server_app.telegram_helpers import tg_send_message

log = logging.getLogger("server")


async def api_print_giao_handler(request: web.Request):
    body = await request.json()
    apply_web_actor(request, body)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"error": "Missing thread_id"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"error": "Order not found"}, status=404)
    result = await execute_print_giao(conn, order, body.get("user_id"))
    if result.get("error"):
        return web.json_response(result, status=409 if "No KiotViet" in result["error"] else 500)
    if state._client:
        printed_by = await resolve_name(body.get("user_id")) if body.get("user_id") else "Hệ thống"
        spawn_tracked("print_giao.notification", tg_send_message(ORDER_GROUP_ID, f"🖨️ {printed_by} đã in 2 hóa đơn (không QR) và Phiếu giao hàng", reply_to=thread_id), {"thread_id": thread_id, "user_id": body.get("user_id")})
    return web.json_response(result)
