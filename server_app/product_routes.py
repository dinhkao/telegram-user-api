"""HTTP tra cứu sản phẩm cho webapp — autocomplete mã/tên SP khi nhập hoá đơn.

GET /api/products?search=&limit= → {ok, products:[{code, name}]}. Đọc từ
product_store (bảng products trong app.db, có cache). Lọc theo mã HOẶC tên
(không phân biệt hoa/thường, bỏ dấu qua vn_normalize). Đăng ký ở app_factory.
"""
from __future__ import annotations

from aiohttp import web

from order_db import _get_connection
from product_store.queries import get_all_products
from vn import vn_normalize


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
