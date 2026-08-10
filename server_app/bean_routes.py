"""HTTP KHO ĐẬU — danh mục + vị trí + dashboard tồn: /api/beans (100% local).

GET /api/beans = dashboard tồn (bảng đậu × kho, đọc được theo đậu HOẶC theo kho;
mỗi loại đậu kèm `units` = đơn vị quy đổi) · CRUD loại đậu (/api/beans/items*) và
kho đậu (/api/beans/places*): tạo = mọi user đăng nhập, sửa = văn phòng, xoá =
admin (xoá mềm, chặn khi còn phiếu). Phiếu nhập/xuất/điều chỉnh ở
server_app/bean_slip_routes.py, đơn vị quy đổi ở bean_unit_routes.py. Nối: bean_store,
server_app.realtime, audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import bean_store
from bean_store import domain
from utils.db import get_connection

log = logging.getLogger("bean_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _actor_type(request: web.Request) -> str:
    return "web_user" if request.get("web_user") else "http_client"


def _conn():
    conn = get_connection()
    bean_store.ensure_tables(conn)
    return conn


def audit(action: str, entity_id, request: web.Request, payload: dict) -> None:
    """Ghi lịch sử thao tác (scope 'bean') — dùng chung với bean_slip_routes."""
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="bean", thread_id=entity_id, actor_type=_actor_type(request),
        actor_id=_actor(request), source=action, payload=payload))


async def _body(request: web.Request) -> dict:
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    return b if isinstance(b, dict) else {}


def _int(request: web.Request, key: str = "id"):
    try:
        return int(request.match_info.get(key, ""))
    except (TypeError, ValueError):
        return None


async def _office(request: web.Request) -> bool:
    from server_app.order_api_common import is_office_request
    return await is_office_request(request)


async def _admin(request: web.Request) -> bool:
    from server_app.order_api_common import is_admin_request
    return await is_admin_request(request)


def _emit() -> None:
    from server_app.realtime import emit_bean_changed
    emit_bean_changed()


# ── Dashboard tồn ────────────────────────────────────────────────────────────
async def beans_dashboard_handler(request: web.Request):
    """GET /api/beans — danh mục + kho + TỒN (by_bean / by_place / tổng)."""
    def _run():
        conn = _conn()
        try:
            beans = bean_store.list_beans(conn)
            units = bean_store.units_by_bean(conn)   # 1 query cho mọi loại đậu
            for b in beans:
                b["units"] = units.get(int(b["id"]), [])
            places = bean_store.list_places(conn)
            cells = bean_store.stock_cells(conn)
            table = domain.build_stock_table(beans, places, cells)
            slips, total = bean_store.list_slips(conn, limit=5)
            return beans, places, table, slips, total
        finally:
            conn.close()
    beans, places, table, slips, slip_total = await asyncio.to_thread(_run)
    return web.json_response({
        "ok": True, "beans": beans, "places": places,
        "by_bean": table["by_bean"], "by_place": table["by_place"], "total": table["total"],
        "recent_slips": slips, "slip_count": slip_total, "today_ymd": domain.today_vn(),
    })


# ── Loại đậu ─────────────────────────────────────────────────────────────────
async def bean_create_handler(request: web.Request):
    """POST /api/beans/items — mọi user đăng nhập thêm loại đậu."""
    body = await _body(request)
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.add_bean(conn, body.get("name") or "",
                                       unit=str(body.get("unit") or "kg"),
                                       note=str(body.get("note") or ""), by=actor)
        finally:
            conn.close()
    bean, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.item_created", bean["id"], request,
          {"bean_id": bean["id"], "bean_name": bean["name"], "unit": bean["unit"]})
    return web.json_response({"ok": True, "bean": bean})


async def bean_update_handler(request: web.Request):
    """POST /api/beans/items/{id} — CHỈ văn phòng sửa tên/đơn vị/ghi chú."""
    if not await _office(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa loại đậu"}, status=403)
    bid = _int(request)
    if bid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await _body(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.update_bean(
                conn, bid,
                name=None if body.get("name") is None else str(body["name"]),
                unit=None if body.get("unit") is None else str(body["unit"]),
                note=None if body.get("note") is None else str(body["note"]))
        finally:
            conn.close()
    bean, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.item_updated", bid, request,
          {"bean_id": bid, "bean_name": bean["name"], "unit": bean["unit"]})
    return web.json_response({"ok": True, "bean": bean})


async def bean_delete_handler(request: web.Request):
    """DELETE /api/beans/items/{id} — CHỈ admin, xoá mềm (chặn khi còn phiếu)."""
    if not await _admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá loại đậu"}, status=403)
    bid = _int(request)
    if bid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            bean = bean_store.get_bean(conn, bid)
            ok, err = bean_store.soft_delete_bean(conn, bid, by=actor)
            return bean, ok, err
        finally:
            conn.close()
    bean, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.item_deleted", bid, request,
          {"bean_id": bid, "bean_name": (bean or {}).get("name") or ""})
    return web.json_response({"ok": True})


# ── Vị trí kho đậu ───────────────────────────────────────────────────────────
async def bean_place_create_handler(request: web.Request):
    """POST /api/beans/places — mọi user đăng nhập thêm kho (Kho A, Kho B…)."""
    body = await _body(request)
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.add_place(conn, body.get("name") or "",
                                        note=str(body.get("note") or ""), by=actor)
        finally:
            conn.close()
    place, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.place_created", place["id"], request,
          {"place_id": place["id"], "place_name": place["name"]})
    return web.json_response({"ok": True, "place": place})


async def bean_place_update_handler(request: web.Request):
    """POST /api/beans/places/{id} — CHỈ văn phòng sửa tên/ghi chú."""
    if not await _office(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa kho"}, status=403)
    pid = _int(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await _body(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.update_place(
                conn, pid,
                name=None if body.get("name") is None else str(body["name"]),
                note=None if body.get("note") is None else str(body["note"]))
        finally:
            conn.close()
    place, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.place_updated", pid, request, {"place_id": pid, "place_name": place["name"]})
    return web.json_response({"ok": True, "place": place})


async def bean_place_delete_handler(request: web.Request):
    """DELETE /api/beans/places/{id} — CHỈ admin, xoá mềm (chặn khi còn phiếu)."""
    if not await _admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá kho"}, status=403)
    pid = _int(request)
    if pid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            place = bean_store.get_place(conn, pid)
            ok, err = bean_store.soft_delete_place(conn, pid, by=actor)
            return place, ok, err
        finally:
            conn.close()
    place, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.place_deleted", pid, request,
          {"place_id": pid, "place_name": (place or {}).get("name") or ""})
    return web.json_response({"ok": True})
