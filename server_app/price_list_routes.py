"""HTTP handlers bảng giá chung (webapp) — /api/price-lists*.

Danh sách bảng giá chung, chi tiết (giá + khách đang dùng), sửa giá (diff → lịch
sử), lịch sử đổi giá từng SP. Nối: price_list_store, order_api_common (web actor).
Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from price_list_store import list_all, get_one, save_prices, set_price, customers_using, get_history
from utils.db import get_connection


async def price_lists_handler(request: web.Request):
    """Tất cả bảng giá chung."""
    data = await asyncio.to_thread(list_all)
    return web.json_response({"ok": True, "lists": data})


async def price_list_detail_handler(request: web.Request):
    """1 bảng giá: giá + khách đang dùng."""
    lid = request.match_info.get("id", "").strip()
    if not lid:
        return web.json_response({"ok": False, "error": "thiếu id"}, status=400)

    def _run():
        one = get_one(lid)
        if one is None:
            return None
        one["customers"] = customers_using(lid)
        return one

    data = await asyncio.to_thread(_run)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy bảng giá"}, status=404)
    return web.json_response({"ok": True, "list": data})


async def price_list_save_handler(request: web.Request):
    """Ghi lại toàn bộ giá (diff → price_history). Body {items:[{sp,price}], name?}."""
    lid = request.match_info.get("id", "").strip()
    if not lid:
        return web.json_response({"ok": False, "error": "thiếu id"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    from server_app.order_api_common import apply_web_actor
    apply_web_actor(request, body, key="user")
    actor = str(body.get("user") or "web")
    items = body.get("items")
    if not isinstance(items, list):
        return web.json_response({"ok": False, "error": "items phải là mảng"}, status=400)
    name = body.get("name") if isinstance(body.get("name"), str) else None

    data = await asyncio.to_thread(save_prices, lid, items, actor, name=name)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy bảng giá"}, status=404)
    data["customers"] = await asyncio.to_thread(customers_using, lid)
    from server_app.realtime import emit_price_lists_changed
    emit_price_lists_changed()
    return web.json_response({"ok": True, "list": data})


async def price_one_save_handler(request: web.Request):
    """Đổi giá 1 SP (view-only + sửa từng dòng). Body {sp, price} → ghi lịch sử."""
    lid = request.match_info.get("id", "").strip()
    if not lid:
        return web.json_response({"ok": False, "error": "thiếu id"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    from server_app.order_api_common import apply_web_actor
    apply_web_actor(request, body, key="user")
    actor = str(body.get("user") or "web")
    sp = str(body.get("sp") or "").strip()
    if not sp:
        return web.json_response({"ok": False, "error": "thiếu mã SP"}, status=400)

    res = await asyncio.to_thread(set_price, lid, sp, body.get("price"), actor)
    if res is None:
        return web.json_response({"ok": False, "error": "không thấy bảng giá"}, status=404)
    if isinstance(res, dict) and res.get("error"):
        return web.json_response({"ok": False, "error": res["error"]}, status=400)
    from server_app.realtime import emit_price_lists_changed
    emit_price_lists_changed()
    return web.json_response({"ok": True, "list": res})


async def price_list_history_handler(request: web.Request):
    """Lịch sử đổi giá của 1 bảng (tuỳ chọn ?sp=<mã> để lọc 1 SP)."""
    lid = request.match_info.get("id", "").strip()
    if not lid:
        return web.json_response({"ok": False, "error": "thiếu id"}, status=400)
    sp = request.query.get("sp", "").strip() or None

    def _run():
        conn = get_connection()
        try:
            return get_history(conn, lid, sp)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "history": rows})
