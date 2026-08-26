"""API JSON /api/profit/* cho dashboard lợi nhuận NATIVE trong webapp (#/loi-nhuan).

Thay bộ trang HTML server-render cũ /loi-nhuan/* (gỡ 2026-08-26) — giờ đi auth
Bearer chuẩn của app, gate CHỈ VĂN PHÒNG (is_office_request). Mọi generator quét
FULL bảng orders nên chạy trong thread với connection RIÊNG (_run) — không gọi
thẳng trên event loop. Logic: profit_dashboard/compute.py + queries.py +
settings.py. Đăng ký qua register() ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

log = logging.getLogger("server")


def _run(fn, *args, **kw):
    """Chạy fn(conn, *args) trong thread với connection riêng."""
    def work():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return fn(conn, *args, **kw)
        finally:
            conn.close()
    return asyncio.to_thread(work)


def _dates(request):
    today = time.strftime("%Y-%m-%d")
    since = (request.query.get("since") or today).strip() or None
    until = (request.query.get("until") or "").strip() or None
    return since, until


async def _office(request) -> bool:
    from server_app.order_api_common import is_office_request
    return await is_office_request(request)


def _deny():
    return web.json_response({"ok": False, "error": "Chỉ văn phòng mới xem được lợi nhuận"}, status=403)


async def profit_dashboard_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.compute import dashboard_data
    from profit_dashboard.settings import load_settings
    since, until = _dates(request)
    st = load_settings()
    product = (request.query.get("product") or "").strip().upper() or None
    customer = (request.query.get("customer") or "").strip() or None
    paid_only = request.query.get("paid") == "1"
    data = await _run(dashboard_data, since, until,
                      int(st.get("yearly_loan_payment") or 0), st.get("monthly_weights"),
                      filter_product=product, filter_customer=customer, paid_only=paid_only)
    return web.json_response({"ok": True, **data})


async def profit_orders_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.queries import orders_feed
    since, until = _dates(request)
    try:
        page = max(1, int(request.query.get("page", 1)))
        per_page = min(200, max(1, int(request.query.get("per_page", 50))))
    except ValueError:
        page, per_page = 1, 50
    product = (request.query.get("product") or "").strip().upper() or None
    customer = (request.query.get("customer") or "").strip() or None
    paid_only = request.query.get("paid") == "1"
    data = await _run(orders_feed, page, per_page, since, until, product, customer,
                      paid_only=paid_only)
    return web.json_response({"ok": True, **data})


async def profit_customers_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.compute import customers_data
    since, until = _dates(request)
    data = await _run(customers_data, since, until)
    return web.json_response({"ok": True, **data})


async def profit_customer_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.compute import customer_detail_data
    name = (request.query.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "thiếu tên khách"}, status=400)
    since, until = _dates(request)
    data = await _run(customer_detail_data, name, since, until)
    return web.json_response({"ok": True, **data})


async def profit_product_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.compute import product_detail_data
    code = request.match_info.get("code", "").strip()
    since, until = _dates(request)
    data = await _run(product_detail_data, code, since, until)
    return web.json_response({"ok": True, **data})


async def profit_settings_get_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.settings import load_settings
    return web.json_response({"ok": True, "settings": load_settings()})


async def profit_settings_save_handler(request: web.Request):
    if not await _office(request):
        return _deny()
    from profit_dashboard.settings import save_settings
    try:
        data = await request.json()
        yearly = int(data.get("yearly_loan_payment", 0))
        if yearly < 0:
            return web.json_response({"ok": False, "error": "Số tiền không hợp lệ"}, status=400)
        raw = data.get("monthly_weights") or {}
        weights = {str(m): max(0.0, float(raw.get(str(m), raw.get(m, 1.0))))
                   for m in range(1, 13)}
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Dữ liệu không hợp lệ"}, status=400)
    if not save_settings({"yearly_loan_payment": yearly, "monthly_weights": weights}):
        return web.json_response({"ok": False, "error": "Lỗi khi lưu"}, status=500)
    return web.json_response({"ok": True})


async def profit_costs_update_handler(request: web.Request):
    """POST {updates: {"MÃ": giá_vốn}} — cập nhật giá vốn hàng loạt (hoặc 1 mã)."""
    if not await _office(request):
        return _deny()
    from product_db import upsert_product
    try:
        body = await request.json()
        raw = body.get("updates") or {}
        updates = []
        for code, cost in raw.items():
            code = str(code).strip().upper()
            cost = int(cost)
            if code and cost >= 0:
                updates.append((code, cost))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Dữ liệu không hợp lệ"}, status=400)
    if not updates:
        return web.json_response({"ok": False, "error": "Không có gì để lưu"}, status=400)

    def apply(conn):
        for code, cost in updates:
            upsert_product(conn, code, cost_price=cost)
    await _run(apply)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    actor = str(request.get("web_user") or "?")
    spawn_tracked("audit.profit_costs", async_log_event(
        "product.costs_updated", actor_type="web", actor_id=actor,
        payload={"count": len(updates), "codes": [c for c, _ in updates][:20]}))
    return web.json_response({"ok": True, "updated": len(updates)})


async def profit_freeze_handler(request: web.Request):
    """POST — đóng băng giá vốn hiện tại vào mọi đơn còn thiếu cost_price."""
    if not await _office(request):
        return _deny()
    from profit_dashboard.queries import freeze_all_costs
    updated = await _run(freeze_all_costs)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.profit_freeze", async_log_event(
        "product.costs_frozen", actor_type="web",
        actor_id=str(request.get("web_user") or "?"), payload={"orders": updated}))
    return web.json_response({"ok": True, "updated": updated})


def register(r) -> None:
    r.add_get("/api/profit/dashboard", profit_dashboard_handler)
    r.add_get("/api/profit/orders", profit_orders_handler)
    r.add_get("/api/profit/customers", profit_customers_handler)
    r.add_get("/api/profit/customer", profit_customer_handler)
    r.add_get("/api/profit/product/{code}", profit_product_handler)
    r.add_get("/api/profit/settings", profit_settings_get_handler)
    r.add_post("/api/profit/settings", profit_settings_save_handler)
    r.add_post("/api/profit/costs", profit_costs_update_handler)
    r.add_post("/api/profit/freeze-costs", profit_freeze_handler)
