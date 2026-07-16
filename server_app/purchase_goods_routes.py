"""HTTP nhập KHO hàng mua về — flow GIỐNG XUẤT KHO ĐƠN (văn phòng, trừ undo=admin).

POST /api/purchases/{id}/receive-goods {dispositions} — ghi nhập TỪNG ĐỢT khi
  phiếu đang mở (restock_new: count thùng × quantity/thùng | restock_existing:
  cộng vào thùng có sẵn). Gọi nhiều lần được.
POST /api/purchases/{id}/confirm-goods — CHỐT: khoá phiếu + snapshot goods_result
  (1 lần/phiếu — CAS); trả missing để UI đã cảnh báo thiếu trước khi gọi.
POST /api/purchases/{id}/unreceive {allocation_id} — gỡ 1 dòng cộng-vào-thùng
  khi phiếu đang mở (thùng mới thì xoá thùng qua /api/inventory/box/{id} DELETE).
POST /api/purchases/{id}/handle-goods — endpoint CŨ: nhập + chốt 1 phát (giữ
  tương thích). /undo-goods — HỦY CHỐT (admin) → phiếu về trạng thái đang nhập.
Nối: server_app.purchase_goods (orchestration), purchase_goods_view (row đọc),
purchase_store, purchase_routes (_actor/_items_display), realtime, audit_log.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from utils.db import get_connection

log = logging.getLogger("purchase_goods_routes")


def _detail_row(conn, pid: int):
    """Row phiếu đầy đủ cho response (items display + boxes + draft_receipt)."""
    from server_app.purchase_routes import _items_display
    from server_app.purchase_goods_view import attach_purchase_boxes, mark_deleted_boxes
    from purchase_store import get_purchase_full
    return attach_purchase_boxes(
        conn, mark_deleted_boxes(conn, _items_display(conn, get_purchase_full(conn, pid))))


def _pid(request) -> int | None:
    try:
        return int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return None


def _emit_goods(pid: int, touched) -> None:
    from server_app.realtime import emit_purchase_changed, emit_inventory_changed, emit_box_changed
    emit_purchase_changed(pid)
    emit_inventory_changed()
    for bid in touched or []:
        emit_box_changed(bid)


def _audit(request, action: str, pid: int, actor: str, payload: dict) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="purchase", thread_id=pid,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source=action, payload=payload))


async def purchase_receive_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/receive-goods (văn phòng) — ghi nhập từng đợt."""
    from server_app.order_api_common import is_office_request
    from server_app.purchase_routes import _actor
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được nhập kho hàng mua"}, status=403)
    pid = _pid(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    dispositions = body.get("dispositions") if isinstance(body.get("dispositions"), list) else []
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import receive_purchase_lines
        conn = get_connection()
        try:
            extra, err = receive_purchase_lines(conn, pid, dispositions, actor=actor)
            if err:
                return None, err, None
            return _detail_row(conn, pid), None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit_goods(pid, extra["touched_boxes"])
    _audit(request, "purchase.goods_line_added", pid, actor,
           {"boxes": len(extra["touched_boxes"]), "supplier_id": extra.get("supplier_id")})
    return web.json_response({"ok": True, "purchase": row})


async def purchase_confirm_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/confirm-goods (văn phòng) — CHỐT nhập kho, khoá phiếu."""
    from server_app.order_api_common import is_office_request
    from server_app.purchase_routes import _actor
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được chốt nhập kho"}, status=403)
    pid = _pid(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import confirm_purchase_receipt
        conn = get_connection()
        try:
            extra, err = confirm_purchase_receipt(conn, pid, actor=actor)
            if err:
                return None, err, None
            return _detail_row(conn, pid), None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if err == "already":
        return web.json_response({"ok": False, "error": "Phiếu này đã chốt nhập kho rồi"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit_goods(pid, extra["touched_boxes"])
    _audit(request, "purchase.goods_received", pid, actor,
           {"result": extra["result"], "missing": extra.get("missing"),
            "supplier_id": extra.get("supplier_id")})
    return web.json_response({"ok": True, "purchase": row, "result": extra["result"],
                              "missing": extra.get("missing") or []})


async def purchase_unreceive_handler(request: web.Request):
    """POST /api/purchases/{id}/unreceive {allocation_id} (văn phòng) — gỡ 1 dòng
    cộng-vào-thùng-có-sẵn khi phiếu đang mở."""
    from server_app.order_api_common import is_office_request
    from server_app.purchase_routes import _actor
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được gỡ dòng nhập kho"}, status=403)
    pid = _pid(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import unreceive_purchase_line
        conn = get_connection()
        try:
            info, err = unreceive_purchase_line(conn, pid, body.get("allocation_id"))
            if err:
                return None, err, None
            return _detail_row(conn, pid), None, info
        finally:
            conn.close()

    row, err, info = await asyncio.to_thread(_run)
    if err:
        status = 404 if "Không tìm thấy" in err else 400
        return web.json_response({"ok": False, "error": err}, status=status)
    _emit_goods(pid, [info["box_id"]])
    _audit(request, "purchase.goods_line_removed", pid, actor,
           {"box_code": info.get("box_code"), "quantity": info.get("quantity"),
            "supplier_id": info.get("supplier_id")})
    return web.json_response({"ok": True, "purchase": row})


async def purchase_handle_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/handle-goods (văn phòng) — nhập + CHỐT 1 phát (cũ)."""
    from server_app.order_api_common import is_office_request
    from server_app.purchase_routes import _actor
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được nhập kho hàng mua"}, status=403)
    pid = _pid(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    dispositions = body.get("dispositions") if isinstance(body.get("dispositions"), list) else []
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import apply_purchase_receipt
        conn = get_connection()
        try:
            extra, err = apply_purchase_receipt(conn, pid, dispositions, actor=actor)
            if err:
                return None, err, None
            return _detail_row(conn, pid), None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if err == "already":
        return web.json_response({"ok": False, "error": "Hàng của phiếu này đã nhập kho rồi"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    result = extra["result"]
    _emit_goods(pid, extra["touched_boxes"] if (result["restocked_existing"] or result["restocked_new"]) else [])
    _audit(request, "purchase.goods_received", pid, actor,
           {"result": result, "supplier_id": extra.get("supplier_id")})
    return web.json_response({"ok": True, "purchase": row, "result": result})


async def purchase_undo_goods_handler(request: web.Request):
    """POST /api/purchases/{id}/undo-goods — HỦY CHỐT nhập kho (CHỈ admin).

    Mở khóa all-or-nothing: giữ nguyên thùng mới + gỡ allocation purchase_in →
    phiếu về trạng thái ĐANG NHẬP (sửa/xoá thùng/nhập thêm/chốt lại). CHẶN nếu
    hàng đã được dùng — lỗi 409 kèm thùng vi phạm."""
    from server_app.order_api_common import is_admin_request
    from server_app.purchase_routes import _actor
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được hủy chốt nhập kho"}, status=403)
    pid = _pid(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _run():
        from server_app.purchase_goods import undo_purchase_receipt
        conn = get_connection()
        try:
            info, err = undo_purchase_receipt(conn, pid)
            if err:
                return None, err, None
            return _detail_row(conn, pid), None, info
        finally:
            conn.close()

    row, err, info = await asyncio.to_thread(_run)
    if err:
        status = 404 if "Không tìm thấy" in err else 409
        return web.json_response({"ok": False, "error": err}, status=status)
    _emit_goods(pid, info.get("retained_boxes"))
    _audit(request, "purchase.goods_undone", pid, actor,
           {"retained_boxes": len(info.get("retained_boxes") or []),
            "removed_allocations": info.get("removed_allocations"),
            "supplier_id": info.get("supplier_id")})
    return web.json_response({"ok": True, "purchase": row})
