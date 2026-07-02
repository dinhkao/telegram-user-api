"""HTTP handlers khách hàng cho web app — GET /api/customers (tìm), GET /api/customers/{key}.

Đọc bảng `customers` (app.db) qua order_store.customers; trả gọn: tên, kh_id,
công nợ (debt), thread_id topic khách. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection, get_customer_by_key, search_customers


def _summary(data: dict, firebase_key: str) -> dict:
    return {
        "key": firebase_key,
        "name": data.get("name") or data.get("ten") or firebase_key,
        "kh_id": data.get("kh_id"),
        "debt": data.get("debt"),
        "debt_updated_at": data.get("debt_updated_at"),
        "thread_id": data.get("thread_id"),
        "last_order_at": data.get("last_order_at"),
    }


async def customers_search_handler(request: web.Request):
    search = request.query.get("search", "").strip()
    sort = request.query.get("sort", "name")
    if sort not in ("name", "recent"):
        sort = "name"
    try:
        limit = max(1, min(50, int(request.query.get("limit", "20"))))
    except ValueError:
        limit = 20

    def _run():
        conn = _get_connection()
        try:
            return search_customers(conn, search, limit=limit, sort=sort)
        finally:
            conn.close()

    results = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "customers": [_summary(c, c.get("_firebase_key", "")) for c in results]})


async def customer_detail_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            return get_customer_by_key(conn, key)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    return web.json_response({"ok": True, "customer": {**_summary(data, key), "price_list": data.get("price_list"), "personal_price_list": data.get("personal_price_list")}})
