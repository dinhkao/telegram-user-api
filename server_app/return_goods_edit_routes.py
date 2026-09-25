"""POST /api/returns/{id}/goods/revert {kind, index} (văn phòng) — GỠ 1 dòng đã xử lý
hàng trả (thùng mới chưa đi đâu / phần cộng vào thùng có sẵn còn nguyên / dòng hủy).
Logic: server_app/return_goods_edit.revert_goods_line. Sau đó: realtime phiếu trả +
kho, event kho (box.deleted / box.return_in_removed) cho timeline thùng/SP/vị trí,
event phiếu `return.goods_reverted`. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


async def return_goods_revert_handler(request: web.Request):
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa xử lý hàng trả"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
        body = await request.json()
        kind = str(body.get("kind") or "")
        index = int(body.get("index"))
    except (TypeError, ValueError, AttributeError):
        return web.json_response({"ok": False, "error": "Dữ liệu không hợp lệ"}, status=400)
    actor = _actor(request)

    def _run():
        from return_store import get_return_full
        from server_app.return_goods_edit import revert_goods_line, with_pending
        from server_app.return_routes import _items_display
        conn = get_connection()
        try:
            extra, err = revert_goods_line(conn, rid, kind, index, actor=actor)
            if err:
                return None, err, None
            return with_pending(conn, _items_display(conn, get_return_full(conn, rid))), None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)

    from server_app.realtime import (emit_box_changed, emit_customer_changed, emit_disposal_changed,
                                     emit_inventory_changed, emit_return_changed)
    emit_return_changed(rid)
    if extra.get("customer_key"):
        emit_customer_changed(extra["customer_key"])
    audit = extra["audit"]
    if audit["deleted"] or audit["return_in_removed"]:
        emit_inventory_changed()
        for s in audit["deleted"] + audit["return_in_removed"]:
            emit_box_changed(s.get("box_id"))
    if extra.get("disposal_id"):
        emit_disposal_changed(extra["disposal_id"])

    at = "web_user" if request.get("web_user") else "http_client"
    from server_app.inventory_audit import log_box_deleted, log_box_deleted_box, log_boxes_return_in_removed
    for s in audit["deleted"]:
        log_box_deleted_box(s, actor=actor, actor_type=at, extra={"return_id": rid})
        if s.get("place_id"):
            log_box_deleted(s, actor=actor, actor_type=at)
    if audit["return_in_removed"]:
        log_boxes_return_in_removed(audit["return_in_removed"], return_id=rid, actor=actor, actor_type=at)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_goods_reverted", async_log_event(
        "return.goods_reverted", scope="return", thread_id=rid, actor_type=at, actor_id=actor,
        source="return.goods_reverted", payload={"kind": extra["kind"], "line": extra["line"],
                                                 "reset": extra["reset"]}))
    return web.json_response({"ok": True, "return": row})
