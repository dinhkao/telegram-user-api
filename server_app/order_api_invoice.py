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


async def _is_admin(request: web.Request) -> bool:
    """Chỉ-admin cho XOÁ HĐ — dùng chung is_admin_request (order_api_common)."""
    from server_app.order_api_common import is_admin_request
    return await is_admin_request(request)


async def api_create_invoice_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    # TẠO hoá đơn: văn phòng (admin/van_phong); XOÁ vẫn chỉ admin (handler dưới)
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo hoá đơn KiotViet"}, status=403)
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
    # Render hình hoá đơn KiotViet → thêm vào gallery đơn (chạy nền, Playwright ~1-2s)
    from server_app.invoice_image import add_invoice_image_to_gallery
    spawn_tracked("invoice.image", add_invoice_image_to_gallery(int(thread_id)), {"thread_id": int(thread_id)})
    return web.json_response({"ok": True, "thread_id": int(thread_id), "kv_code": result["kv_code"],
                              "kv_id": result["kv_id"], "old_debt": result["old_debt"]})


async def api_delete_invoice_handler(request: web.Request):
    """Xoá hoá đơn KiotViet của đơn — CHỈ user có role 'admin' trong web_users.
    Body {thread_id, user_id?}. Xoá HĐ trên KiotViet + gỡ kiotvietInvoiceID/Code."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    if not await _is_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá hoá đơn KiotViet"}, status=403)
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


async def api_refresh_debt_handler(request: web.Request):
    """Kéo nợ KiotViet mới nhất của khách → lưu làm snapshot nợ của đơn
    (khDebt + invoice_debt_snapshot). Body {thread_id}."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    # Đơn đã có HĐ KiotViet → nợ đã chốt theo hoá đơn, không cho kéo nợ mới (tránh ghi đè)
    if order.get("kiotvietInvoiceID"):
        return web.json_response({"ok": False, "error": "Đơn đã có hoá đơn KiotViet — không kéo nợ được"}, status=400)
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        return web.json_response({"ok": False, "error": "Đơn chưa có khách hàng"}, status=400)
    customer = get_customer_by_key(conn, str(kh_id_fb))
    if not customer or not customer.get("kh_id"):
        return web.json_response({"ok": False, "error": "Không tìm thấy ID KiotViet của khách"}, status=400)
    try:
        from kiotviet import get_customer_debt_kv
        det = await asyncio.to_thread(get_customer_debt_kv, customer["kh_id"])
    except Exception as e:
        log.error("refresh debt failed thread=%s: %s", thread_id, e)
        return web.json_response({"ok": False, "error": f"Lỗi lấy nợ KiotViet: {e}"}, status=500)
    debt = det.get("debt", 0)
    order["khDebt"] = debt
    order["invoice_debt_snapshot"] = debt
    from order_db import _save_order, update_customer_debt
    _save_order(conn, int(thread_id), order)
    update_customer_debt(conn, str(kh_id_fb), debt)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("debt.refresh", refresh_order_bg(conn, int(thread_id), order["channel_id"], order["message_id"]), {"thread_id": int(thread_id)})
    return web.json_response({"ok": True, "thread_id": int(thread_id), "debt": debt})


async def api_ensure_invoice_image_handler(request: web.Request):
    """POST /api/order/{thread_id}/invoice-image/ensure — bảo đảm gallery có ảnh HĐ.

    Nút 'Xem HĐ' gọi: đã có ảnh kind='hoa_don' → trả ngay; chưa có (render nền từng
    lỗi/HĐ tạo qua Telegram) → render PNG + lưu gallery NGAY (đợi xong) rồi trả ảnh."""
    thread_id = request.match_info.get("thread_id", "").strip()
    if not thread_id.lstrip("-").isdigit():
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    tid = int(thread_id)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, tid)
    if not order:
        return web.json_response({"ok": False, "error": "Không tìm thấy đơn"}, status=404)
    if not order.get("kiotvietInvoiceID"):
        return web.json_response({"ok": False, "error": "Đơn chưa có hoá đơn KiotViet"}, status=400)
    from order_images_store import list_images
    imgs = await asyncio.to_thread(list_images, tid)
    have = [i for i in imgs if i.get("kind") == "hoa_don" or i.get("uploaded_by") == "KiotViet HĐ"]
    if have:
        return web.json_response({"ok": True, "image": have[0], "created": False})   # list mới nhất trước
    from server_app.invoice_image import add_invoice_image_to_gallery
    img = await add_invoice_image_to_gallery(tid)
    if not img:
        return web.json_response({"ok": False, "error": "Render ảnh hoá đơn lỗi — thử lại"}, status=502)
    return web.json_response({"ok": True, "image": img, "created": True})


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
