"""HTTP tạo hoá đơn KiotViet cho webapp — tương đương lệnh 'tạo hd' trong topic.

POST /api/order/invoice/create-kiotviet {thread_id, user_id?}. Dùng chung core
order_commands_v3._process_create_invoice_core (đọc invoice/khách/VAT/PVC/CK từ
đơn → tạo HĐ KiotViet → ghi lại kiotvietInvoiceID/Code + snapshot nợ + đánh dấu
'bán HĐ'). Sau đó refresh main message (kèm realtime) + thông báo 'bán HĐ' vào
topic. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from order_db import _get_connection, get_customer_by_key, get_order_by_thread_id

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


async def api_delete_invoice_handler(request: web.Request):
    """Xoá hoá đơn KiotViet của đơn — CHỈ user admin (ADMIN_WEB_USER, mặc định 'duy').
    Body {thread_id, user_id?}. Xoá HĐ trên KiotViet + gỡ kiotvietInvoiceID/Code."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    from server_app.config import ADMIN_WEB_USER
    actor = request.get("web_user") or str(body.get("user_id") or "")
    if actor != ADMIN_WEB_USER:
        return web.json_response({"ok": False, "error": f"Chỉ {ADMIN_WEB_USER} mới được xoá hoá đơn"}, status=403)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    invoice_id = order.get("kiotvietInvoiceID")
    if not invoice_id:
        return web.json_response({"ok": False, "error": "Đơn không có hoá đơn KiotViet"}, status=400)
    try:
        from kiotviet import delete_invoice_kv
        await asyncio.to_thread(delete_invoice_kv, int(invoice_id))
    except Exception as e:
        log.error("delete invoice failed thread=%s id=%s: %s", thread_id, invoice_id, e)
        return web.json_response({"ok": False, "error": f"Lỗi xoá HĐ KiotViet: {e}"}, status=500)
    order.pop("kiotvietInvoiceID", None)
    order.pop("kiotvietInvoiceCode", None)
    from order_db import _save_order
    _save_order(conn, int(thread_id), order)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("invoice.refresh", refresh_order_bg(conn, int(thread_id), order["channel_id"], order["message_id"]), {"thread_id": int(thread_id)})
    return web.json_response({"ok": True, "thread_id": int(thread_id)})


async def api_invoice_html_handler(request: web.Request):
    """Trả HTML hoá đơn KiotViet đã render để webapp mở xem (tương đương 'get html').
    Fetch invoice từ KiotViet nên chạy trong thread để không chặn event loop."""
    thread_id = request.match_info.get("thread_id", "").strip()
    if not thread_id.lstrip("-").isdigit():
        return web.Response(text="thread_id không hợp lệ", status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if not order:
        return web.Response(text="Không tìm thấy đơn hàng", status=404)
    invoice_id = order.get("kiotvietInvoiceID")
    if not invoice_id:
        return web.Response(text="Đơn chưa có hoá đơn KiotViet — bấm Tạo HĐ trước.", status=400)
    kh_name = "Khách hàng"
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if kh_id_fb:
        c = get_customer_by_key(conn, str(kh_id_fb))
        if c:
            kh_name = c.get("name", "Khách hàng")
    debt = order.get("invoice_debt_snapshot", 0) or 0
    try:
        from renderers.inhoadon import generate_invoice_html
        html = await asyncio.to_thread(
            generate_invoice_html, int(invoice_id), debt,
            {"customerNameOverride": kh_name, "expectedVAT": 0, "expectedPVC": 0, "disableQR": True},
        )
    except Exception as e:
        log.error("invoice-html render failed thread=%s: %s", thread_id, e)
        return web.Response(text=f"Lỗi tạo HTML hoá đơn: {e}", status=500)
    return web.Response(text=html, content_type="text/html")
