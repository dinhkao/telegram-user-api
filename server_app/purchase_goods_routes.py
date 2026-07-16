"""HTTP nhập KHO hàng mua về — POST /api/purchases/{id}/handle-goods (văn phòng).

body {dispositions: [{sp, quantity, action, box_id?, place_id?, unit_id?}]}
  action = 'restock_new' (tạo thùng mới, gắn source_purchase_id)
         | 'restock_existing' (nhập vào thùng có sẵn — allocation ÂM 'purchase_in')
         | 'skip'.
Idempotent-guard: phiếu đã nhập kho → 409 (tránh nhập 2 lần). Tách file riêng vì
purchase_routes.py đã chạm trần 400 dòng. Nối: server_app.purchase_goods (orchestration),
purchase_store, server_app.purchase_routes (_actor/_items_display), realtime, audit_log.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from utils.db import get_connection

log = logging.getLogger("purchase_goods_routes")


async def purchase_handle_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/handle-goods (văn phòng) — nhập kho hàng mua về."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được nhập kho hàng mua"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    dispositions = body.get("dispositions") if isinstance(body.get("dispositions"), list) else []
    from server_app.purchase_routes import _actor, _items_display
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import apply_purchase_receipt
        from purchase_store import get_purchase_full
        conn = get_connection()
        try:
            extra, err = apply_purchase_receipt(conn, pid, dispositions, actor=actor)
            if err:
                return None, err, None
            updated = _items_display(conn, get_purchase_full(conn, pid))
            return updated, None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if err == "already":
        return web.json_response({"ok": False, "error": "Hàng của phiếu này đã nhập kho rồi"}, status=409)

    from server_app.realtime import emit_purchase_changed, emit_inventory_changed, emit_box_changed
    emit_purchase_changed(pid)
    result = extra["result"]
    if result["restocked_existing"] or result["restocked_new"]:
        emit_inventory_changed()
        for bid in extra["touched_boxes"]:
            emit_box_changed(bid)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_goods", async_log_event(
        "purchase.goods_received", scope="purchase", thread_id=pid,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="purchase.goods_received",
        payload={"result": result, "supplier_id": extra.get("supplier_id")}))
    return web.json_response({"ok": True, "purchase": row, "result": result})


async def purchase_undo_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/undo-goods — HỦY CHỐT nhập kho (CHỈ admin).

    Hoàn tác all-or-nothing: xoá thùng mới tạo từ phiếu + gỡ allocation purchase_in
    + clear goods_handled_* → phiếu mở khoá sửa/nhập kho lại. CHẶN nếu hàng đã
    được dùng (thùng mới có lần xuất/chuyển, hoặc phần cộng vào thùng có sẵn đã
    tiêu) — lỗi 409 kèm thùng vi phạm."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được hủy chốt nhập kho"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    from server_app.purchase_routes import _actor, _items_display
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import undo_purchase_receipt
        from purchase_store import get_purchase_full
        conn = get_connection()
        try:
            info, err = undo_purchase_receipt(conn, pid)
            if err:
                return None, err, None
            updated = _items_display(conn, get_purchase_full(conn, pid))
            return updated, None, info
        finally:
            conn.close()

    row, err, info = await asyncio.to_thread(_run)
    if err:
        status = 404 if "Không tìm thấy" in err else 409
        return web.json_response({"ok": False, "error": err}, status=status)

    from server_app.realtime import emit_purchase_changed, emit_inventory_changed, emit_box_changed
    emit_purchase_changed(pid)
    emit_inventory_changed()
    for bid in info.get("deleted_boxes") or []:
        emit_box_changed(bid)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_goods_undo", async_log_event(
        "purchase.goods_undone", scope="purchase", thread_id=pid,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="purchase.goods_undone",
        payload={"deleted_boxes": len(info.get("deleted_boxes") or []),
                 "removed_allocations": info.get("removed_allocations"),
                 "supplier_id": info.get("supplier_id")}))
    return web.json_response({"ok": True, "purchase": row})
