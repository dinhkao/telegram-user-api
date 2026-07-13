"""HTTP phiếu XUẤT HỦY hàng hóa — /api/disposals (100% local, không KiotViet).

GET list / POST tạo (văn phòng, body {picks: [{box_id, quantity?}], reason}) /
GET {id} / POST {id}/delete xoá (admin — TỒN HOÀN LẠI các thùng, phiếu xoá mềm).
Trừ tồn qua box_allocations kind='disposal' nên tồn thùng giảm ngay khi tạo.
Nối: disposal_store, inventory_store (allocations), server_app.realtime, audit_log.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import disposal_store
from utils.db import get_connection

log = logging.getLogger("disposal_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _conn():
    conn = get_connection()
    disposal_store.ensure_table(conn)
    return conn


async def disposals_all_handler(request: web.Request):
    """GET /api/disposals — dashboard xuất hủy (mới nhất trước)."""
    def _run():
        conn = _conn()
        try:
            return disposal_store.list_disposals(conn)
        finally:
            conn.close()
    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "disposals": rows})


async def disposal_detail_handler(request: web.Request):
    """GET /api/disposals/{id} — chi tiết 1 phiếu hủy."""
    try:
        did = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _get():
        conn = _conn()
        try:
            return disposal_store.get_disposal(conn, did)
        finally:
            conn.close()
    row = await asyncio.to_thread(_get)
    if not row:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu hủy"}, status=404)
    return web.json_response({"ok": True, "disposal": row})


async def disposal_create_handler(request: web.Request):
    """POST /api/disposals (văn phòng) — body {picks: [{box_id, quantity?}], reason}."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được xuất hủy"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    picks = body.get("picks") if isinstance(body.get("picks"), list) else []
    reason = str(body.get("reason") or "").strip()
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            slip, err = disposal_store.create_disposal(conn, picks, reason=reason, by=actor)
            audit_items = []
            if slip:
                from server_app.inventory_audit import box_snapshot
                for item in slip["items"]:
                    snap = box_snapshot(conn, item.get("box_id"))
                    if snap:
                        audit_items.append({**snap, "taken": item.get("quantity")})
            return slip, err, audit_items
        finally:
            conn.close()
    slip, err, audit_items = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)

    from server_app.realtime import emit_box_changed, emit_disposal_changed, emit_inventory_changed
    emit_disposal_changed(slip["id"])
    emit_inventory_changed()   # tồn các SP liên quan đổi
    for item in slip["items"]:
        emit_box_changed(item.get("box_id"))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    from server_app.inventory_audit import log_boxes_disposed
    log_boxes_disposed(
        audit_items, disposal_id=slip["id"], reason=reason, actor=actor,
        actor_type="web_user" if request.get("web_user") else "http_client",
    )
    spawn_tracked("audit.disposal_created", async_log_event(
        "disposal.created", scope="disposal", thread_id=slip["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="disposal.created",
        payload={"reason": reason, "items": slip["items"], "total_quantity": slip["total_quantity"]}))
    return web.json_response({"ok": True, "disposal": slip})


async def disposal_delete_handler(request: web.Request):
    """POST /api/disposals/{id}/delete (CHỈ admin) — hoàn tồn + xoá mềm phiếu."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu hủy"}, status=403)
    try:
        did = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            slip = disposal_store.get_disposal(conn, did)
            restored, err = disposal_store.delete_disposal(conn, did, by=actor)
            audit_items = []
            if slip and not err:
                from server_app.inventory_audit import box_snapshot
                for item in slip.get("items", []):
                    snap = box_snapshot(conn, item.get("box_id"))
                    if snap:
                        audit_items.append({**snap, "taken": item.get("quantity")})
            return slip, restored, err, audit_items
        finally:
            conn.close()
    slip, restored, err, audit_items = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    from server_app.realtime import emit_box_changed, emit_disposal_changed, emit_inventory_changed
    emit_disposal_changed(did)
    emit_inventory_changed()
    for item in (slip or {}).get("items", []):
        emit_box_changed(item.get("box_id"))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    from server_app.inventory_audit import log_boxes_disposal_released
    log_boxes_disposal_released(
        audit_items, disposal_id=did, reason=(slip or {}).get("reason"), actor=actor,
        actor_type="web_user" if request.get("web_user") else "http_client",
    )
    spawn_tracked("audit.disposal_deleted", async_log_event(
        "disposal.deleted", scope="disposal", thread_id=did,
        actor_type="web_user", actor_id=actor, source="disposal.deleted",
        payload={"restored_allocations": restored, "items": (slip or {}).get("items", [])}))
    return web.json_response({"ok": True, "restored": restored})
