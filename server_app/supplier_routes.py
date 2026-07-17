"""HTTP NHÀ CUNG CẤP — /api/suppliers (100% local, không KiotViet).

GET list (kèm thống kê phiếu nhập) / POST tạo (văn phòng) / GET {id} (kèm phiếu
nhập của NCC) / POST {id} sửa (văn phòng) / POST {id}/delete xoá mềm (admin).
Nối: supplier_store, purchase_store, server_app.realtime, audit_log.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from supplier_store import (add_supplier, get_supplier, list_suppliers,
                            soft_delete_supplier, update_supplier)
from utils.db import get_connection

log = logging.getLogger("supplier_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


async def suppliers_list_handler(request: web.Request):
    """GET /api/suppliers — mọi NCC + thống kê (số phiếu, tổng tiền, lần nhập cuối)."""
    def _run():
        conn = get_connection()
        try:
            return list_suppliers(conn)
        finally:
            conn.close()
    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "suppliers": rows})


async def supplier_create_handler(request: web.Request):
    """POST /api/suppliers (mọi người dùng đăng nhập — mở cùng tạo phiếu nhập
    2026-07-17: trang tạo phiếu gõ tên NCC lạ là tạo NCC ngay). Body {name,
    phone?, address?, note?}. Sửa NCC vẫn văn phòng, xoá vẫn admin."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Thiếu tên nhà cung cấp"}, status=400)
    actor = _actor(request)

    def _save():
        conn = get_connection()
        try:
            return add_supplier(conn, name, phone=str(body.get("phone") or "").strip(),
                                address=str(body.get("address") or "").strip(),
                                note=str(body.get("note") or "").strip(), by=actor)
        finally:
            conn.close()
    row = await asyncio.to_thread(_save)

    from server_app.realtime import emit_supplier_changed
    emit_supplier_changed(row["id"])
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.supplier_created", async_log_event(
        "supplier.created", scope="supplier", thread_id=row["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="supplier.created", payload={"name": name}))
    return web.json_response({"ok": True, "supplier": row})


async def supplier_detail_handler(request: web.Request):
    """GET /api/suppliers/{id} — chi tiết NCC + mọi phiếu nhập của NCC đó."""
    try:
        sid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            sup = get_supplier(conn, sid)
            if not sup:
                return None, []
            from purchase_store import list_purchases_for_supplier
            return sup, list_purchases_for_supplier(conn, sid)
        finally:
            conn.close()
    sup, purchases = await asyncio.to_thread(_run)
    if not sup:
        return web.json_response({"ok": False, "error": "Không tìm thấy nhà cung cấp"}, status=404)
    return web.json_response({"ok": True, "supplier": sup, "purchases": purchases})


async def supplier_update_handler(request: web.Request):
    """POST /api/suppliers/{id} (văn phòng) — sửa name/phone/address/note (ô nào gửi mới sửa)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa nhà cung cấp"}, status=403)
    try:
        sid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if "name" in body and not str(body.get("name") or "").strip():
        return web.json_response({"ok": False, "error": "Tên nhà cung cấp không được rỗng"}, status=400)

    def _run():
        conn = get_connection()
        try:
            if not get_supplier(conn, sid):
                return False
            update_supplier(conn, sid,
                            name=body.get("name"), phone=body.get("phone"),
                            address=body.get("address"), note=body.get("note"))
            return True
        finally:
            conn.close()
    ok = await asyncio.to_thread(_run)
    if not ok:
        return web.json_response({"ok": False, "error": "Không tìm thấy nhà cung cấp"}, status=404)
    from server_app.realtime import emit_supplier_changed
    emit_supplier_changed(sid)
    return web.json_response({"ok": True})


async def supplier_delete_handler(request: web.Request):
    """POST /api/suppliers/{id}/delete (CHỈ admin) — xoá mềm; chặn nếu còn phiếu nhập."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá nhà cung cấp"}, status=403)
    try:
        sid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            sup = get_supplier(conn, sid)
            if not sup or sup.get("deleted_at"):
                return "notfound"
            from purchase_store import list_purchases_for_supplier
            if list_purchases_for_supplier(conn, sid):
                return "has_purchases"
            soft_delete_supplier(conn, sid, by=_actor(request))
            return "ok"
        finally:
            conn.close()
    res = await asyncio.to_thread(_run)
    if res == "notfound":
        return web.json_response({"ok": False, "error": "Không tìm thấy nhà cung cấp"}, status=404)
    if res == "has_purchases":
        return web.json_response(
            {"ok": False, "error": "NCC còn phiếu nhập — xoá các phiếu nhập trước", "locked": True}, status=400)
    from server_app.realtime import emit_supplier_changed
    emit_supplier_changed(sid)
    actor = _actor(request)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.supplier_deleted", async_log_event(
        "supplier.deleted", scope="supplier", thread_id=sid,
        actor_type="web_user", actor_id=actor, source="supplier.deleted", payload={}))
    return web.json_response({"ok": True})
