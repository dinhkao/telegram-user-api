from __future__ import annotations

import logging
import os

from aiohttp import web

from order_db import _get_connection, clear_task_status, get_customer_by_key, get_order_by_thread_id, _save_order, transaction
from product_db import freeze_invoice_cost_prices

from server_app import state
from server_app.order_api_common import refresh_order_bg
from server_app.tasks import spawn_tracked
from server_app.telegram_helpers import tg_send_message

log = logging.getLogger("server")


async def api_fix_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id, text = body.get("thread_id"), (body.get("text") or "").strip()
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)
    conn = _get_connection()
    with transaction(conn):   # atomic RMW; the async _auto_parse_fix runs AFTER, outside the lock
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        order["text"] = order["text_raw"] = text
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    from order_commands_v3 import _auto_parse_fix
    spawn_tracked("order.auto_parse_fix", _auto_parse_fix(state._client, conn, thread_id, text), {"thread_id": thread_id})
    return web.json_response({"ok": True})


async def api_assign_customer_handler(request: web.Request):
    """Gán khách cho đơn — set khach_hang_id + customer_name (→ has_customer=1).
    Body {thread_id, customer_key}. Dùng cho section Khách hàng ở trang chi tiết."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id, customer_key = body.get("thread_id"), body.get("customer_key")
    if not thread_id or not customer_key:
        return web.json_response({"ok": False, "error": "Missing thread_id or customer_key"}, status=400)
    conn = _get_connection()
    customer = get_customer_by_key(conn, str(customer_key))
    if not customer:
        return web.json_response({"ok": False, "error": "Không tìm thấy khách hàng"}, status=404)
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        order["khach_hang_id"] = str(customer_key)
        order["customer_name"] = customer.get("name", "")
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, order["channel_id"], order["message_id"]), {"thread_id": thread_id})
    return web.json_response({"ok": True, "customer_name": customer.get("name", ""), "customer_key": str(customer_key)})


async def api_set_ngay_giao_handler(request: web.Request):
    """Đặt ngày giao dự kiến cho đơn. Body {thread_id, ngay_giao} — chuỗi
    'YYYY-MM-DDTHH:MM' (hoặc '' / null để xoá). Đánh dấu ngay_giao_auto=False (sửa tay)."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    val = body.get("ngay_giao")
    val = str(val).strip()[:16] if val else None   # cắt còn YYYY-MM-DDTHH:MM
    conn = _get_connection()
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        order["ngay_giao"] = val
        order["ngay_giao_auto"] = False
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, order["channel_id"], order["message_id"]), {"thread_id": thread_id})
    return web.json_response({"ok": True, "ngay_giao": val})


async def api_invoice_update_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id, invoice = body.get("thread_id"), body.get("invoice")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    if invoice is not None and not isinstance(invoice, list):
        return web.json_response({"ok": False, "error": "invoice must be a list"}, status=400)
    conn = _get_connection()
    with transaction(conn):   # atomic RMW; the async refresh runs AFTER, outside the lock
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        if invoice is not None:
            order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
        # Điều chỉnh (chiết khấu / PVC / VAT) — chỉ set khi client gửi kèm
        for k in ("vat", "pvc", "discount"):
            if k in body:
                try:
                    order[k] = int(body[k] or 0)
                except (TypeError, ValueError):
                    order[k] = 0
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, order["channel_id"], order["message_id"]), {"thread_id": thread_id, "channel_id": order["channel_id"], "message_id": order["message_id"]})
    log.info("invoice-update: thread=%d items=%d", thread_id, len(invoice or []))
    return web.json_response({"ok": True})


async def api_reply_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id, text, times = body.get("thread_id"), (body.get("text") or "").strip(), body.get("times", 1)
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)
    try:
        for _ in range(min(times, 5)):
            await tg_send_message(int(os.getenv("ORDER_GROUP_ID", "-1002124542200")), text, reply_to=thread_id)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True})


async def api_refresh_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    conn = _get_connection()
    if not get_order_by_thread_id(conn, thread_id):
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    return web.json_response({"ok": True})
