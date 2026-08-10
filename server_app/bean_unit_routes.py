"""HTTP QUY ĐỔI ĐƠN VỊ kho đậu — /api/beans/items/{id}/units* (100% local).

GET danh sách đơn vị của 1 loại đậu · POST thêm (mọi user đăng nhập) ·
POST {uid} sửa tên/tỉ lệ (văn phòng) · DELETE {uid} xoá (admin — phiếu cũ không
hỏng vì đã lưu snapshot đơn vị và số trong DB vốn theo đơn vị gốc).
Nối: bean_store.units, server_app.bean_routes (_conn/audit dùng chung).
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

import bean_store
from server_app.bean_routes import audit
from utils.db import get_connection


def _conn():
    conn = get_connection()
    bean_store.ensure_tables(conn)
    return conn


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _emit() -> None:
    from server_app.realtime import emit_bean_changed
    emit_bean_changed()


def _ids(request: web.Request) -> tuple[int | None, int | None]:
    def _one(key):
        try:
            return int(request.match_info.get(key, ""))
        except (TypeError, ValueError):
            return None
    return _one("id"), _one("uid")


async def _body(request: web.Request) -> dict:
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    return b if isinstance(b, dict) else {}


async def bean_units_handler(request: web.Request):
    """GET /api/beans/items/{id}/units — đơn vị quy đổi + đơn vị gốc của loại đậu."""
    bid, _ = _ids(request)
    if bid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            bean = bean_store.get_bean(conn, bid)
            return bean, (bean_store.list_units(conn, bid) if bean else [])
        finally:
            conn.close()
    bean, units = await asyncio.to_thread(_run)
    if not bean:
        return web.json_response({"ok": False, "error": "Không tìm thấy loại đậu"}, status=404)
    return web.json_response({"ok": True, "base_unit": bean["unit"], "units": units})


async def bean_unit_add_handler(request: web.Request):
    """POST /api/beans/items/{id}/units {name, factor} — mọi user đăng nhập.
    factor = 1 <đơn vị này> bằng bao nhiêu ĐƠN VỊ GỐC."""
    bid, _ = _ids(request)
    if bid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await _body(request)
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            bean = bean_store.get_bean(conn, bid)
            if not bean:
                return None, None, "Không tìm thấy loại đậu"
            unit, err = bean_store.add_unit(conn, bid, body.get("name") or "",
                                            body.get("factor"), bean["unit"],
                                            note=str(body.get("note") or ""), by=actor)
            return bean, unit, err
        finally:
            conn.close()
    bean, unit, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err},
                                 status=404 if bean is None else 400)
    _emit()
    audit("bean.unit_created", bid, request,
          {"bean_id": bid, "bean_name": bean["name"], "unit_name": unit["name"],
           "factor": unit["factor"], "base_unit": bean["unit"]})
    return web.json_response({"ok": True, "unit": unit})


async def bean_unit_update_handler(request: web.Request):
    """POST /api/beans/items/{id}/units/{uid} — CHỈ văn phòng sửa tên/tỉ lệ.

    ⚠ Sửa tỉ lệ KHÔNG tính lại phiếu cũ: mỗi dòng phiếu đã quy về đơn vị gốc và
    lưu snapshot hệ số lúc nhập, nên tồn quá khứ giữ nguyên (cố ý).
    """
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa đơn vị"}, status=403)
    bid, uid = _ids(request)
    if bid is None or uid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await _body(request)

    def _save():
        conn = _conn()
        try:
            bean = bean_store.get_bean(conn, bid)
            if not bean:
                return None, None, "Không tìm thấy loại đậu"
            cur = bean_store.get_unit(conn, uid)
            if not cur or int(cur["bean_id"]) != bid:
                return bean, None, "Đơn vị không thuộc loại đậu này"
            unit, err = bean_store.update_unit(
                conn, uid,
                name=None if body.get("name") is None else str(body["name"]),
                factor=body.get("factor"),
                note=None if body.get("note") is None else str(body["note"]),
                base_unit=bean["unit"])
            return bean, unit, err
        finally:
            conn.close()
    bean, unit, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err},
                                 status=404 if bean is None else 400)
    _emit()
    audit("bean.unit_updated", bid, request,
          {"bean_id": bid, "bean_name": bean["name"], "unit_name": unit["name"],
           "factor": unit["factor"], "base_unit": bean["unit"]})
    return web.json_response({"ok": True, "unit": unit})


async def bean_unit_delete_handler(request: web.Request):
    """DELETE /api/beans/items/{id}/units/{uid} — CHỈ admin."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá đơn vị"}, status=403)
    bid, uid = _ids(request)
    if bid is None or uid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _del():
        conn = _conn()
        try:
            bean = bean_store.get_bean(conn, bid)
            if not bean:
                return None, None, "Không tìm thấy loại đậu"
            cur = bean_store.get_unit(conn, uid)
            if not cur or int(cur["bean_id"]) != bid:
                return bean, None, "Đơn vị không thuộc loại đậu này"
            unit, err = bean_store.delete_unit(conn, uid)
            return bean, unit, err
        finally:
            conn.close()
    bean, unit, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err},
                                 status=404 if bean is None else 400)
    _emit()
    audit("bean.unit_deleted", bid, request,
          {"bean_id": bid, "bean_name": bean["name"], "unit_name": unit["name"],
           "factor": unit["factor"], "base_unit": bean["unit"]})
    return web.json_response({"ok": True})
