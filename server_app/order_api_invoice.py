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

from order_db import _get_connection, _save_order, get_customer_by_key, get_order_by_thread_id, transaction
from order_store.tasks import set_task_status

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
    # Phối hợp UI: báo cho các client KHÁC "đang có người tạo HĐ" → khoá nút + tắt
    # popup xác nhận của họ (backend vẫn chống trùng bằng _invoice_create_lock). Nhả
    # tín hiệu trong finally dù thành công hay lỗi.
    from server_app.production_routes import _web_actor
    from server_app.realtime import emit_invoice_creating
    holder = _web_actor(request, body) or "văn phòng"
    emit_invoice_creating(int(thread_id), holder)
    try:
        from order_commands_v3 import _process_create_invoice_core
        result = await _process_create_invoice_core(int(thread_id), user_id)
    except Exception as e:
        log.error("create invoice API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    finally:
        emit_invoice_creating(int(thread_id), None)
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
    # Đơn đã CHỐT xuất kho → HĐ khớp phần đã xuất. Xoá HĐ mà giữ chốt kho làm lệch
    # sổ (đã trừ tồn nhưng không còn HĐ). Có đường HUỶ CHỐT (admin) → bắt huỷ trước.
    if isinstance(order.get("stock_confirmed"), dict) and order["stock_confirmed"]:
        return web.json_response({"ok": False, "error":
            "Đơn đã chốt xuất kho — huỷ chốt xuất kho trước rồi mới xoá HĐ KiotViet"}, status=400)
    try:
        from kiotviet import delete_invoice_kv
        await asyncio.to_thread(delete_invoice_kv, int(invoice_id))
    except Exception as e:
        log.error("delete invoice failed thread=%s id=%s: %s", thread_id, invoice_id, e)
        return web.json_response({"ok": False, "error": f"Lỗi xoá HĐ KiotViet: {e}"}, status=500)
    # RE-READ trong transaction SAU await KiotViet: chỉ gỡ 2 field HĐ trên bản mới
    # nhất, không ghi đè blob bằng bản đọc trước await (mất update xen kẽ).
    with transaction(conn):
        fresh = get_order_by_thread_id(conn, int(thread_id))
        if fresh:
            fresh.pop("kiotvietInvoiceID", None)
            fresh.pop("kiotvietInvoiceCode", None)
            _save_order(conn, int(thread_id), fresh)
            order = fresh
    # HĐ không còn tồn tại thì bước "bán HĐ" cũng không thể giữ trạng thái xong.
    # Dùng cùng quy tắc với lệnh Telegram `del hd` để cập nhật cả order lẫn
    # bảng task mirror trên dashboard VIỆC.
    actor = request.get("web_user") or body.get("user_id")
    set_task_status(conn, int(thread_id), "ban_hd", actor, done=False)
    # Xoá MỀM luôn ảnh HOÁ ĐƠN của đơn (render từ HĐ vừa xoá — giữ lại chỉ gạch X)
    def _soft_del_hoadon_imgs():
        from order_images_store import list_images, delete_image
        by = str(request.get("web_user") or body.get("user_id") or "?")
        ids = []
        for im in list_images(int(thread_id)):
            if im.get("kind") == "hoa_don" and not im.get("deleted_at"):
                if delete_image(im["id"], int(thread_id), by=by):
                    ids.append(im["id"])
        return by, ids
    by, img_ids = await asyncio.to_thread(_soft_del_hoadon_imgs)
    if img_ids:
        from audit_log import async_log_event
        for iid in img_ids:
            spawn_tracked("audit.image_deleted", async_log_event(
                "order.image_deleted", actor_type="web", actor_id=by,
                thread_id=int(thread_id), payload={"image_id": iid, "reason": "xoá HĐ KiotViet"}))
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("invoice.refresh", refresh_order_bg(conn, int(thread_id), order["channel_id"], order["message_id"]), {"thread_id": int(thread_id)})
    return web.json_response({"ok": True, "thread_id": int(thread_id)})


async def api_set_invoice_reference_image_handler(request: web.Request):
    """Lưu vĩnh viễn ảnh tham chiếu khi sửa HĐ. Body {thread_id, image_id|null}.

    Chỉ chấp nhận ảnh thuộc đúng pool của đơn và chưa bị xoá tại thời điểm chọn.
    image_id=null là bỏ ảnh tham chiếu.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    try:
        thread_id = int(body.get("thread_id"))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)

    raw_image_id = body.get("image_id")
    if raw_image_id in (None, ""):
        image_id = None
    else:
        try:
            image_id = int(raw_image_id)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "image_id không hợp lệ"}, status=400)
        from order_images_store import get_image
        image = get_image(image_id)
        if not image or int(image.get("thread_id") or 0) != thread_id or image.get("deleted_at"):
            return web.json_response({"ok": False, "error": "Ảnh không thuộc đơn hoặc đã bị xoá"}, status=400)

    conn = _get_connection()
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        if image_id is None:
            order.pop("invoice_reference_image_id", None)
        else:
            order["invoice_reference_image_id"] = image_id
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)

    from server_app.realtime import emit_order_changed
    emit_order_changed(thread_id)
    return web.json_response({"ok": True, "thread_id": thread_id, "image_id": image_id})


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
    from order_db import _save_order, update_customer_debt
    # RE-READ trong transaction SAU await KiotViet: vá 2 field nợ trên bản mới nhất
    # (không ghi đè blob bằng bản đọc trước await); re-check chưa có HĐ — HĐ có thể
    # vừa được tạo trong lúc chờ (nợ khi đó đã chốt theo hoá đơn).
    with transaction(conn):
        fresh = get_order_by_thread_id(conn, int(thread_id))
        if not fresh:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        if fresh.get("kiotvietInvoiceID"):
            return web.json_response({"ok": False, "error": "Đơn đã có hoá đơn KiotViet — không kéo nợ được"}, status=400)
        fresh["khDebt"] = debt
        fresh["invoice_debt_snapshot"] = debt
        _save_order(conn, int(thread_id), fresh)
        order = fresh
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
