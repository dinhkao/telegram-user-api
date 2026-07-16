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


def _paid_total(order: dict) -> int:
    """Tổng tiền ĐÃ THU của đơn (Σ amount các phiếu thu)."""
    return int(sum(int(p.get("amount") or 0) for p in order.get("payments", [])))


def _invoice_total(invoice: list | None, vat, pvc, discount) -> int:
    """Tổng đơn theo đúng công thức webapp: Σ(giá×SL) − chiết_khấu + pvc + vat."""
    goods = 0.0
    for it in invoice or []:
        if not isinstance(it, dict):
            continue
        try:
            goods += float(it.get("price") or 0) * float(it.get("sl", it.get("quantity", 0)) or 0)
        except (TypeError, ValueError):
            pass
    return int(round(goods - int(discount or 0) + int(pvc or 0) + int(vat or 0)))


def _stock_locked_price_update(order: dict, invoice: list | None, body: dict) -> list[dict] | None:
    """Sau CHỐT XUẤT KHO chỉ khoá HÀNG ĐÃ XUẤT: không thêm/xoá dòng, không đổi mã,
    không đổi số lượng (kho đã trừ theo đó). Còn lại sửa hết: giá, ghi chú từng
    dòng, chiết khấu, PVC, VAT (xử lý ở caller). Trả invoice dựng lại từ bản cũ
    (giữ metadata nội bộ cost_price/id...) hoặc None nếu payload đụng phần khoá."""
    old_invoice = order.get("invoice") or []
    new_invoice = invoice if invoice is not None else old_invoice
    try:
        same_lines = len(new_invoice) == len(old_invoice) and all(
            isinstance(new, dict)
            and str(new.get("sp") or "").strip().upper() == str(old.get("sp") or "").strip().upper()
            and float(new.get("sl", new.get("quantity", 0)) or 0) == float(old.get("sl", old.get("quantity", 0)) or 0)
            for old, new in zip(old_invoice, new_invoice)
        )
        if not same_lines:
            return None
        return [
            {**old, "price": int(float(new.get("price") or 0)), "note": str(new.get("note") or "")}
            for old, new in zip(old_invoice, new_invoice)
        ]
    except (TypeError, ValueError, OverflowError):
        return None


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
        if order.get("stock_confirmed"):
            return web.json_response(
                {"ok": False, "error": "Đơn đã chốt xuất kho — chỉ được sửa đơn giá", "locked": True},
                status=403,
            )
        order["text"] = order["text_raw"] = text
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    from order_commands_v3 import _auto_parse_fix
    # keep_customer (trang sửa hoá đơn): giữ khách đã gán, KHÔNG nhận diện lại từ text
    reassign = not bool(body.get("keep_customer"))
    spawn_tracked("order.auto_parse_fix", _auto_parse_fix(state._client, conn, thread_id, text, reassign_customer=reassign), {"thread_id": thread_id})
    # Phát realtime NGAY (auto_parse chỉ emit khi có invoice; sửa text không SP sẽ mất push)
    from server_app.realtime import emit_order_changed
    emit_order_changed(thread_id)
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
        if order.get("stock_confirmed"):
            return web.json_response(
                {"ok": False, "error": "Đơn đã chốt xuất kho — chỉ được sửa đơn giá", "locked": True},
                status=403,
            )
        # HĐ KiotViet đã tạo theo khách cũ — đổi khách làm HĐ/nợ lệch → cấm (xoá HĐ trước)
        if order.get("kiotvietInvoiceID"):
            return web.json_response(
                {"ok": False, "error": "Đơn đã có hoá đơn KiotViet — không đổi khách được. Xoá hoá đơn trước."},
                status=400)
        # Đã có phiếu thu — tiền + snapshot nợ (old_debt/new_debt) gắn khách HIỆN TẠI;
        # đổi khách sẽ làm timeline/công nợ lệch sang khách khác → cấm (xoá phiếu thu trước)
        if order.get("payments"):
            return web.json_response(
                {"ok": False, "error": "Đơn đã có thanh toán — không đổi khách được (tiền đã gắn khách hiện tại). Xoá phiếu thu trước rồi mới đổi."},
                status=400)
        order["khach_hang_id"] = str(customer_key)
        order["customer_name"] = customer.get("name", "")
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    # Việc mặc định của khách → auto-thêm vào đơn (transaction riêng, trước refresh)
    from order_store.custom_tasks import apply_customer_default_tasks
    apply_customer_default_tasks(conn, thread_id, str(customer_key))
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


async def api_set_no_track_handler(request: web.Request):
    """Bật/tắt 'Bỏ theo dõi nợ' cho đơn. Body {thread_id, on}. Bật: đơn chưa có
    thanh toán hiện 😑 (thay 😡) và KHÔNG tính vào chip lọc Nợ ở dashboard."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    on = bool(body.get("on"))
    conn = _get_connection()
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        if on:
            order["bo_theo_doi_no"] = True
        else:
            order.pop("bo_theo_doi_no", None)
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    if order.get("channel_id") and order.get("message_id") and state._client is not None:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, order["channel_id"], order["message_id"]), {"thread_id": thread_id})
    return web.json_response({"ok": True, "bo_theo_doi_no": on})


async def api_set_bypass_debt_handler(request: web.Request):
    """Bật/tắt cờ riêng ``bypass_debt``. Cờ này CHỈ loại đơn khỏi trang tạo
    thanh toán; không thay đổi icon nợ, chip lọc nợ hay ``bo_theo_doi_no``."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    on = bool(body.get("on"))
    conn = _get_connection()
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        if on:
            order["bypass_debt"] = True
        else:
            order.pop("bypass_debt", None)
        if not _save_order(conn, thread_id, order):
            return web.json_response({"ok": False, "error": "Failed to save"}, status=500)
    from server_app.realtime import emit_order_changed
    emit_order_changed(int(thread_id))
    return web.json_response({"ok": True, "bypass_debt": on})


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
        # Sau khi chốt kho chỉ khoá HÀNG ĐÃ XUẤT (mã + số lượng, không thêm/xoá dòng);
        # giá, ghi chú, chiết khấu, PVC, VAT vẫn sửa được. Dựng lại từ invoice cũ để
        # client không thể làm mất metadata nội bộ (cost_price, id...) bằng payload thủ công.
        if order.get("stock_confirmed"):
            price_update = _stock_locked_price_update(order, invoice, body)
            if price_update is None:
                return web.json_response(
                    {"ok": False, "error": "Đơn đã chốt xuất kho — không thêm/xoá mã hàng hay đổi số lượng được (giá, ghi chú, CK, PVC, VAT vẫn sửa được)", "locked": True},
                    status=403,
                )
            invoice = price_update
        if invoice is not None:
            order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
        # Điều chỉnh (chiết khấu / PVC / VAT) — chỉ set khi client gửi kèm
        for k in ("vat", "pvc", "discount"):
            if k in body:
                try:
                    order[k] = int(body[k] or 0)
                except (TypeError, ValueError):
                    order[k] = 0
        # Đã thu tiền rồi mà sửa tổng đơn XUỐNG DƯỚI số đã thu → nợ âm / dư tiền vô lý
        # (giống guard phiếu nhập). Muốn giảm sâu phải xoá bớt phiếu thu trước.
        paid = _paid_total(order)
        if paid > 0:
            new_total = _invoice_total(order.get("invoice"), order.get("vat"), order.get("pvc"), order.get("discount"))
            if new_total < paid:
                return web.json_response(
                    {"ok": False, "error": f"Đơn đã thu {paid:,}đ — tổng mới {new_total:,}đ không được thấp hơn số đã thu. Xoá bớt phiếu thu trước nếu cần giảm.", "locked": True},
                    status=400)
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
