"""DELETE /api/order/{thread_id} — admin xoá đơn (soft-delete) CHỈ KHI đơn KHÔNG có
hoá đơn KiotViet, KHÔNG còn thanh toán nào, và KHÔNG còn phân bổ hàng trong kho.
Nối: order_store.delete_order, inventory_store.list_order_allocations,
realtime.emit_orders_changed.
"""
from __future__ import annotations
import asyncio
import logging

from aiohttp import web

from utils.db import get_connection
from order_store import delete_order
from order_store.serialization import get_order_by_thread_id
from inventory_store import list_order_allocations
from server_app.order_api_common import is_admin_request

log = logging.getLogger(__name__)


async def order_delete_handler(request: web.Request):
    """Xoá đơn — CHỈ admin. Chặn nếu còn HĐ KiotViet hoặc còn phân bổ kho."""
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá đơn"}, status=403)
    try:
        thread_id = int(request.match_info["thread_id"])
    except (KeyError, ValueError, TypeError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            order = get_order_by_thread_id(conn, thread_id, include_deleted=False)
            if not order:
                return "notfound", None
            if order.get("kiotvietInvoiceID"):
                return "invoice", None
            if order.get("payments"):
                return "payment", len(order["payments"])
            allocs = list_order_allocations(conn, thread_id, kind="order")
            if allocs:
                return "alloc", len(allocs)
            ok, msg = delete_order(conn, thread_id, force=True)
            if ok:
                try:
                    conn.execute("DELETE FROM orders_fts WHERE thread_id = ?", (thread_id,))
                    conn.commit()
                except Exception:  # bảng FTS có thể chưa tạo — bỏ qua
                    pass
            return ("ok", None) if ok else ("err", msg)
        finally:
            conn.close()

    status, extra = await asyncio.to_thread(_run)
    if status == "notfound":
        return web.json_response({"ok": False, "error": "Không tìm thấy đơn"}, status=404)
    if status == "invoice":
        return web.json_response({"ok": False, "error": "Đơn còn hoá đơn KiotViet — xoá hoá đơn trước khi xoá đơn"}, status=400)
    if status == "payment":
        return web.json_response({"ok": False, "error": f"Đơn còn {extra} thanh toán — xoá thanh toán trước khi xoá đơn"}, status=400)
    if status == "alloc":
        return web.json_response({"ok": False, "error": f"Đơn còn phân bổ kho ({extra} thùng) — thu hồi hàng về kho trước"}, status=400)
    if status == "err":
        return web.json_response({"ok": False, "error": extra or "Lỗi xoá đơn"}, status=400)
    from server_app.realtime import emit_orders_changed
    emit_orders_changed()
    return web.json_response({"ok": True})
