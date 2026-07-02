"""HTTP tạo hoá đơn KiotViet cho webapp — tương đương lệnh 'tạo hd' trong topic.

POST /api/order/invoice/create-kiotviet {thread_id, user_id?}. Dùng chung core
order_commands_v3._process_create_invoice_core (đọc invoice/khách/VAT/PVC/CK từ
đơn → tạo HĐ KiotViet → ghi lại kiotvietInvoiceID/Code + snapshot nợ + đánh dấu
'bán HĐ'). Sau đó refresh main message (kèm realtime) + thông báo 'bán HĐ' vào
topic. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id

from server_app import state
from server_app.order_api_common import apply_web_actor, refresh_order_bg, resolve_name, send_task_notification
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")


async def api_create_invoice_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    thread_id, user_id = body.get("thread_id"), body.get("user_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    try:
        from order_commands_v3 import _process_create_invoice_core
        result = await _process_create_invoice_core(int(thread_id), user_id)
    except Exception as e:
        log.error("create invoice API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    if not result["success"]:
        return web.json_response({"ok": False, "error": result["error"]}, status=400)
    # refresh main message (đã kèm realtime emit) + thông báo bán HĐ — chạy nền
    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if order and order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("invoice.refresh", refresh_order_bg(conn, int(thread_id), order["channel_id"], order["message_id"]),
                      {"thread_id": int(thread_id)})
        name = await resolve_name(user_id) if user_id else "web"
        spawn_tracked("invoice.notify", send_task_notification(int(thread_id), f"{name} bán HĐ"))
    return web.json_response({"ok": True, "thread_id": int(thread_id), "kv_code": result["kv_code"],
                              "kv_id": result["kv_id"], "old_debt": result["old_debt"]})
