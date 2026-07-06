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
from product_store.queries import get_all_products, sync_kiotviet_products
from vn import vn_normalize

log = logging.getLogger("server")


async def products_sync_kiotviet_handler(request: web.Request):
    """Đồng bộ danh mục KiotViet → products (liên kết code↔KiotViet). POST, không body.
    Kéo toàn bộ sản phẩm KiotViet rồi upsert kv_id/tên. Trả số dòng đã đồng bộ."""
    def _run():
        from integrations.kiotviet import list_all_products_kv
        kv = list_all_products_kv()
        conn = _get_connection()
        try:
            n = sync_kiotviet_products(conn, kv)
        finally:
            conn.close()
        return len(kv), n
    try:
        fetched, synced = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        log.error("Đồng bộ KiotViet products lỗi: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "fetched": fetched, "synced": synced})


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
