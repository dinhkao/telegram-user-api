"""HTTP tra cứu sản phẩm cho webapp — autocomplete mã/tên SP khi nhập hoá đơn.

GET /api/products?search=&limit= → {ok, products:[{code, name}]}. Đọc từ
product_store (bảng products trong app.db, có cache). Lọc theo mã HOẶC tên
(không phân biệt hoa/thường, bỏ dấu qua vn_normalize). Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from order_db import _get_connection
from product_store.queries import get_all_products, get_product, upsert_product, set_kiotviet_link, clear_kiotviet_link
from vn import vn_normalize

log = logging.getLogger("server")


async def product_create_handler(request: web.Request):
    """Tạo mã SP mới (danh mục local). Body {code, name?}. Trùng mã → trả mã sẵn có."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = (body.get("code") or "").upper().strip()
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã SP"}, status=400)
    name = (body.get("name") or "").strip()

    def _run():
        conn = _get_connection()
        try:
            existed = get_product(conn, code) is not None
            upsert_product(conn, code, name=name or None)
            return get_product(conn, code), existed
        finally:
            conn.close()
    product, existed = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "product": product, "existed": existed})


async def product_kiotviet_search_handler(request: web.Request):
    """Tìm sản phẩm KiotViet để liên kết (từng cái). GET ?q= → [{id, code, full_name}]."""
    q = (request.query.get("q") or "").strip()
    if len(q) < 2:
        return web.json_response({"ok": True, "products": []})
    try:
        from integrations.kiotviet import search_products_kv
        products = await asyncio.to_thread(search_products_kv, q, 20)
    except Exception as e:  # noqa: BLE001
        log.error("Tìm SP KiotViet lỗi: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True, "products": products})


def _code(request):
    return (request.match_info.get("code") or "").upper().strip()


async def product_link_handler(request: web.Request):
    """Liên kết 1 mã SP với 1 sản phẩm KiotViet. Body {kv_id, kv_full_name?}."""
    code = _code(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    kv_id = body.get("kv_id")
    if not code or not kv_id:
        return web.json_response({"ok": False, "error": "Thiếu code / kv_id"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            return set_kiotviet_link(conn, code, int(kv_id), body.get("kv_full_name") or "")
        finally:
            conn.close()
    product = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Không tìm thấy mã SP"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "product": product})


async def product_unlink_handler(request: web.Request):
    """Bỏ liên kết KiotViet của 1 mã SP."""
    code = _code(request)

    def _run():
        conn = _get_connection()
        try:
            return clear_kiotviet_link(conn, code)
        finally:
            conn.close()
    product = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Không tìm thấy mã SP"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "product": product})


async def products_search_handler(request: web.Request):
    q = vn_normalize(request.query.get("search", "").strip())
    try:
        limit = max(1, min(50, int(request.query.get("limit", "20"))))
    except ValueError:
        limit = 20
    conn = _get_connection()
    products = get_all_products(conn)
    if q:
        products = [p for p in products
                    if q in vn_normalize(p["code"]) or q in vn_normalize(p.get("name") or "")]
    out = [{"code": p["code"], "name": p.get("name") or ""} for p in products[:limit]]
    return web.json_response({"ok": True, "products": out})
