from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id, get_customer_price_list

from server_app import state
from server_app.order_api_common import apply_web_actor, is_admin_request, refresh_order_bg
from server_app.tasks import spawn_tracked
from server_app.telegram_helpers import tg_send_message

log = logging.getLogger("server")


async def payment_delete_handler(request: web.Request):
    """Xoá 1 thanh toán của đơn — CHỈ user role 'admin'. Body {thread_id, payment_id}.
    Xoá TRÊN KiotViet trước (các payment trong kiotvietData.payments[]), nếu lỗi thì
    GIỮ NGUYÊN local (tránh lệch). Sau đó xoá record local (delete_payment_record) →
    refresh main message + realtime."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá thanh toán"}, status=403)
    thread_id, payment_id = body.get("thread_id"), body.get("payment_id")
    if not thread_id or not payment_id:
        return web.json_response({"ok": False, "error": "Missing thread_id or payment_id"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    pay = next((p for p in order.get("payments", []) if p.get("id") == str(payment_id)), None)
    if not pay:
        return web.json_response({"ok": False, "error": f"Không tìm thấy payment: {payment_id}"}, status=400)
    # 1) Best-effort xoá trên KiotViet. Thanh toán được tạo bằng workaround POST
    # /orders (create_order_with_payment) nên KHÔNG có payment độc lập — phải xoá cả
    # phiếu đặt hàng (DH), id = kiotvietData.id → payment nhúng mất theo. Không chặn:
    # lỗi thì vẫn xoá local + trả cảnh báo.
    kv = pay.get("kiotvietData") or {}
    kv_order_id = kv.get("id")
    kv_warning = ""
    if kv_order_id:
        try:
            from kiotviet import delete_order_kv
            await asyncio.to_thread(delete_order_kv, int(kv_order_id))
        except Exception as e:
            log.warning("delete KV order failed (bỏ qua, xoá local) thread=%s order_id=%s: %s", thread_id, kv_order_id, e)
            kv_warning = "KiotViet không xoá được phiếu đặt hàng — vào app KiotViet xoá tay nếu cần."
    # 2) Xoá record local (nợ tự tính lại từ danh sách payments)
    from payment_store import delete_payment_record
    ok, message = delete_payment_record(conn, int(thread_id), str(payment_id))
    if not ok:
        return web.json_response({"ok": False, "error": message}, status=400)
    # Xoá phiếu thu sổ quỹ gắn payment tiền mặt này (nếu có) → sổ quỹ khớp
    try:
        from quy_store import delete_by_payment
        if delete_by_payment(conn, str(payment_id)):
            from server_app.realtime import emit_quy_changed
            emit_quy_changed()
    except Exception as e:
        log.warning("Xoá phiếu thu sổ quỹ theo payment thất bại: %s", e)
    order = get_order_by_thread_id(conn, int(thread_id))
    if order and order.get("channel_id") and order.get("message_id") and state._client is not None:
        # refresh_order_bg tự phát realtime ở cuối
        spawn_tracked("payment.delete.refresh",
                      refresh_order_bg(conn, int(thread_id), order["channel_id"], order["message_id"]),
                      {"thread_id": int(thread_id)})
    else:
        from server_app.realtime import emit_order_changed
        emit_order_changed(int(thread_id))
    return web.json_response({"ok": True, "thread_id": int(thread_id), "payment_id": str(payment_id), "kv_warning": kv_warning})


async def _payment_handler(request: web.Request, method: str):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo thanh toán"}, status=403)
    apply_web_actor(request, body)
    thread_id, amount, user_id = body.get("thread_id"), body.get("amount"), body.get("user_id")
    if not thread_id or not amount:
        return web.json_response({"ok": False, "error": "Missing thread_id or amount"}, status=400)
    try:
        from order_commands_v3 import _process_payment_core
        result = await _process_payment_core(int(thread_id), int(amount), user_id, method)
    except Exception as e:
        log.error("Payment API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    if not result["success"]:
        return web.json_response({"ok": False, "error": result["error"]}, status=400)
    # Render + gửi phiếu thu PNG vào topic đơn — GIỐNG luồng Telegram (_handle_payment
    # bước 11). Web trước đây bỏ qua bước này. Chạy nền, không chặn response.
    if state._client is not None:
        try:
            from receipt_print import send_payment_receipt
            spawn_tracked("payment.receipt", send_payment_receipt(
                client=state._client, thread_id=result["thread_id"],
                customer_name=result["kh_name"], payment_amount=result["amount"],
                old_debt=result["old_debt"], new_debt=result["new_debt"]),
                {"thread_id": result["thread_id"]})
        except Exception as e:  # noqa: BLE001 — phiếu thu lỗi không được làm hỏng thanh toán
            log.warning("Gửi phiếu thu (web) lỗi thread=%s: %s", result["thread_id"], e)
    return web.json_response({"ok": True, "thread_id": result["thread_id"], "amount": result["amount"], "method": result["method"], "method_label": result["method_label"], "kv_code": result["kv_code"], "old_debt": result["old_debt"], "new_debt": result["new_debt"]})


async def payment_tm_handler(request: web.Request):
    return await _payment_handler(request, "Cash")


async def payment_ck_handler(request: web.Request):
    return await _payment_handler(request, "Transfer")


async def order_totals_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    try:
        conn = _get_connection()
        order = get_order_by_thread_id(conn, int(thread_id))
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        invoice = order.get("invoice") or order.get("san_pham") or []
        total = sum(int(item.get("price", 0)) * int(item.get("sl", 1)) for item in invoice)
        discount, pvc, vat = order.get("discount", 0), order.get("pvc", 0), order.get("vat", 0)
        pre_debt_total = total - discount + pvc + vat
        return web.json_response({"ok": True, "order": {"pre_debt_total": pre_debt_total, "total_payable": pre_debt_total, "total": total, "discount": discount, "pvc": pvc, "vat": vat}})
    except Exception as e:
        log.error("Totals API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def api_customer_price_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    customer_id, product = body.get("customer_id"), (body.get("product") or "").upper().strip()
    if not customer_id or not product:
        return web.json_response({"ok": False, "error": "Missing customer_id or product"}, status=400)
    conn = _get_connection()
    from order_store.search import get_customer_price_source
    price, source, list_name = get_customer_price_source(conn, str(customer_id), product)
    return web.json_response({"ok": True, "price": price, "product": product, "source": source, "list_name": list_name})
