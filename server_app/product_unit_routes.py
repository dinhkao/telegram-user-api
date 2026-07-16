"""API QUY ĐỔI ĐƠN VỊ hàng hoá — /api/products/{code}/units*.

GET (đăng nhập) trả đơn vị gốc + list quy đổi; thêm/sửa = VĂN PHÒNG, xoá = ADMIN
(như các sửa đổi danh mục SP khác). Ghi audit product.unit_* (scope='product',
khoá products.id) + realtime inventory_changed. Nối: product_store.units,
product_store.queries (resolve mã → id), server_app.order_api_common (quyền).
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection
from product_store.queries import get_product
from product_store import units as pu


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    return str((u or {}).get("display_name") or (u or {}).get("username") or "web") if isinstance(u, dict) else str(u or "web")


def _audit(action: str, product: dict, actor: str, **extra) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="product", thread_id=product.get("id"),
        actor_type="web_user", actor_id=actor, source=action,
        payload={"code": product.get("code"), "base_unit": product.get("unit") or "cây", **extra}))


def _load_product(code: str) -> dict | None:
    conn = _get_connection()
    try:
        return get_product(conn, (code or "").upper().strip())
    finally:
        conn.close()


async def _product_or_404(request: web.Request):
    code = (request.match_info.get("code") or "").upper().strip()
    product = await asyncio.to_thread(_load_product, code)
    if not product or not product.get("id"):
        return None, web.json_response({"ok": False, "error": "Mã SP không tồn tại"}, status=404)
    return product, None


async def product_units_list_handler(request: web.Request):
    """GET → {ok, base_unit, units:[{id,name,factor,note}]}."""
    product, err = await _product_or_404(request)
    if err:
        return err

    def _run():
        conn = _get_connection()
        try:
            return pu.list_units(conn, int(product["id"]))
        finally:
            conn.close()
    units = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "product_id": product["id"],
                              "base_unit": product.get("unit") or "cây", "units": units})


async def product_unit_add_handler(request: web.Request):
    """POST {name, factor} — thêm đơn vị quy đổi (VĂN PHÒNG). factor = 1 <name> bằng
    bao nhiêu đơn vị gốc."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    product, err = await _product_or_404(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        body = {}

    def _run():
        conn = _get_connection()
        try:
            return pu.add_unit(conn, int(product["id"]), str(body.get("name") or ""),
                               body.get("factor"), product.get("unit") or "cây")
        finally:
            conn.close()
    unit, uerr = await asyncio.to_thread(_run)
    if uerr:
        return web.json_response({"ok": False, "error": uerr}, status=400)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit("product.unit_added", product, _actor(request), unit=unit["name"], factor=unit["factor"])
    return web.json_response({"ok": True, "unit": unit})


async def product_unit_update_handler(request: web.Request):
    """POST {name, factor} — sửa 1 đơn vị quy đổi (VĂN PHÒNG)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    product, err = await _product_or_404(request)
    if err:
        return err
    try:
        uid = int(request.match_info.get("unit_id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "unit_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}

    def _run():
        conn = _get_connection()
        try:
            return pu.update_unit(conn, int(product["id"]), uid, str(body.get("name") or ""),
                                  body.get("factor"), product.get("unit") or "cây")
        finally:
            conn.close()
    unit, uerr = await asyncio.to_thread(_run)
    if uerr:
        return web.json_response({"ok": False, "error": uerr}, status=400)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit("product.unit_updated", product, _actor(request), unit=unit["name"], factor=unit["factor"])
    return web.json_response({"ok": True, "unit": unit})


async def product_unit_delete_handler(request: web.Request):
    """DELETE — xoá 1 đơn vị quy đổi (ADMIN, như xoá danh mục khác)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá đơn vị"}, status=403)
    product, err = await _product_or_404(request)
    if err:
        return err
    try:
        uid = int(request.match_info.get("unit_id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "unit_id không hợp lệ"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            return pu.delete_unit(conn, int(product["id"]), uid)
        finally:
            conn.close()
    unit = await asyncio.to_thread(_run)
    if not unit:
        return web.json_response({"ok": False, "error": "Không tìm thấy đơn vị"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit("product.unit_deleted", product, _actor(request), unit=unit["name"], factor=unit["factor"])
    return web.json_response({"ok": True})


def register(r: web.UrlDispatcher) -> None:
    r.add_get("/api/products/{code}/units", product_units_list_handler)
    r.add_post("/api/products/{code}/units", product_unit_add_handler)
    r.add_post("/api/products/{code}/units/{unit_id}", product_unit_update_handler)
    r.add_delete("/api/products/{code}/units/{unit_id}", product_unit_delete_handler)
