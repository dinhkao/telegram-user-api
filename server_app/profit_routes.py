"""Dashboard LỢI NHUẬN dưới /loi-nhuan/* — CHỈ VĂN PHÒNG (tiền lãi nhạy cảm).

Trang HTML server-render port từ repo profit-dashboard (package profit_dashboard/).
Vào từ webapp: menu ☰ Thêm → Lợi nhuận (#/loi-nhuan redirect kèm ?token=). Lượt mở
đầu mang token trên query → đóng dấu cookie `pd_token` (Path=/loi-nhuan) để các link
giữa các trang (không mang token) vẫn qua gate. Mọi generator chạy trong thread với
connection riêng (quét full bảng orders — cấm chạy trên event loop).
Nói chuyện với: profit_dashboard/ (pages + queries + settings), product_store,
server_app.production_wages.is_office_username.
"""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

_COOKIE = "pd_token"
_PREFIX = "/loi-nhuan"


def _cookie_username(request) -> str | None:
    tok = (request.cookies.get(_COOKIE) or "").strip()
    if not tok:
        return None
    from server_app.web_auth.secret import get_web_auth_secret
    from server_app.web_auth.token import verify_token
    return verify_token(get_web_auth_secret(), tok, now=int(time.time()))


async def _office_user(request) -> str | None:
    """Username nếu là văn phòng — token từ web_auth (?token=/Bearer) hoặc cookie."""
    username = request.get("web_user") or _cookie_username(request)
    if not username:
        return None
    from server_app.production_wages import is_office_username
    ok = await asyncio.to_thread(is_office_username, username)
    return username if ok else None


def _deny() -> web.Response:
    return web.Response(
        text="<h3>Chỉ văn phòng được xem trang lợi nhuận. Mở từ app: menu ☰ Thêm → Lợi nhuận.</h3>",
        content_type="text/html", status=403)


def _stamp_cookie(request, resp):
    """Lượt vào đầu mang ?token= hợp lệ → giữ lại bằng cookie cho các trang sau."""
    tok = (request.query.get("token") or "").strip()
    if tok and request.get("web_user"):
        resp.set_cookie(_COOKIE, tok, path=_PREFIX, httponly=True,
                        max_age=30 * 24 * 3600, samesite="Lax")
    return resp


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


async def profit_index_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    if "since" not in request.query and "until" not in request.query:
        today = time.strftime("%Y-%m-%d")
        tok = (request.query.get("token") or "").strip()
        extra = f"&token={tok}" if tok else ""
        return _stamp_cookie(request, web.HTTPFound(
            f"{_PREFIX}/?since={today}&until={today}{extra}"))
    from profit_dashboard.pages import generate_dashboard_html
    from profit_dashboard.settings import load_settings, DEFAULT_WEIGHTS
    since, until = _dates(request)
    product = (request.query.get("product") or "").strip().upper() or None
    customer = (request.query.get("customer") or "").strip() or None
    s = load_settings()
    html = await _run(generate_dashboard_html, product, customer,
                      since_date=since, until_date=until,
                      yearly_loan=s.get("yearly_loan_payment", 0),
                      monthly_weights=s.get("monthly_weights", DEFAULT_WEIGHTS))
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_customers_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    if "since" not in request.query and "until" not in request.query:
        today = time.strftime("%Y-%m-%d")
        return _stamp_cookie(request, web.HTTPFound(
            f"{_PREFIX}/customers?since={today}&until={today}"))
    from profit_dashboard.pages import generate_customer_profit_html
    since, until = _dates(request)
    html = await _run(generate_customer_profit_html, since, until)
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_settings_page_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    from profit_dashboard.pages import generate_settings_html
    from profit_dashboard.settings import load_settings, DEFAULT_WEIGHTS
    s = load_settings()
    html = generate_settings_html(s.get("yearly_loan_payment", 0),
                                  s.get("monthly_weights", DEFAULT_WEIGHTS))
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_settings_save_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return web.json_response({"error": "forbidden"}, status=403)
    from profit_dashboard.settings import save_settings
    try:
        data = await request.json()
        yearly_loan = int(data.get("yearly_loan_payment", 0))
        if yearly_loan < 0:
            return web.json_response({"error": "Số tiền không hợp lệ"}, status=400)
        raw = data.get("monthly_weights", {})
        weights = {str(m): max(0.0, float(raw.get(str(m), raw.get(m, 1.0))))
                   for m in range(1, 13)}
        if save_settings({"yearly_loan_payment": yearly_loan, "monthly_weights": weights}):
            return web.json_response({"success": True})
        return web.json_response({"error": "Lỗi khi lưu"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def profit_product_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    from profit_dashboard.pages import generate_product_detail_html
    since, until = _dates(request)
    code = request.match_info["code"].upper()
    html = await _run(generate_product_detail_html, code, since_date=since, until_date=until)
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_customer_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    from urllib.parse import unquote
    from profit_dashboard.pages import generate_customer_detail_html
    name = unquote(request.match_info["name"])
    product = (request.query.get("product") or "").strip().upper() or None
    since, until = _dates(request)
    html = await _run(generate_customer_detail_html, name, product, since, until)
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_order_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _stamp_cookie(request, _deny())
    from profit_dashboard.pages import generate_order_detail_html
    try:
        thread_id = int(request.match_info["thread_id"])
    except ValueError:
        return _deny()
    html = await _run(generate_order_detail_html, thread_id)
    return _stamp_cookie(request, web.Response(text=html, content_type="text/html"))


async def profit_cost_update_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _deny()
    from product_db import upsert_product
    code = request.match_info["code"].upper()
    data = await request.post()
    try:
        cost_price = int(data.get("cost_price", 0))
    except (TypeError, ValueError):
        cost_price = 0
    await _run(upsert_product, code, cost_price=cost_price)
    return web.HTTPFound(f"{_PREFIX}/product/{code}")


async def profit_bulk_update_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return _deny()
    from product_db import upsert_product
    data = await request.post()
    updates = []
    for key, value in data.items():
        if key.startswith("cost_") and str(value).strip():
            try:
                cost = int(str(value).replace(",", "").replace(".", ""))
            except ValueError:
                continue
            if cost >= 0:
                updates.append((key[5:].upper(), cost))

    def apply(conn):
        for code, cost in updates:
            upsert_product(conn, code, cost_price=cost)
    await _run(apply)
    return web.HTTPFound(f"{_PREFIX}/?tab=products")


async def profit_orders_feed_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return web.json_response({"error": "forbidden"}, status=403)
    from profit_dashboard.queries import orders_feed
    since, until = _dates(request)
    page = int(request.query.get("page", 1))
    per_page = int(request.query.get("per_page", 50))
    product = (request.query.get("product") or "").strip().upper() or None
    customer = (request.query.get("customer") or "").strip() or None
    data = await _run(orders_feed, page, per_page, since, until, product, customer)
    return web.json_response(data)


async def profit_freeze_costs_handler(request: web.Request) -> web.Response:
    if not await _office_user(request):
        return web.json_response({"error": "forbidden"}, status=403)
    from profit_dashboard.queries import freeze_all_costs
    updated = await _run(freeze_all_costs)
    return web.json_response({"ok": True, "updated": updated})


def register(r) -> None:
    r.add_get(f"{_PREFIX}/", profit_index_handler)
    r.add_get(_PREFIX, profit_index_handler)   # không / cuối → cùng trang
    r.add_get(f"{_PREFIX}/customers", profit_customers_handler)
    r.add_get(f"{_PREFIX}/settings", profit_settings_page_handler)
    r.add_post(f"{_PREFIX}/api/settings", profit_settings_save_handler)
    r.add_get(f"{_PREFIX}/product/{{code}}", profit_product_handler)
    r.add_get(f"{_PREFIX}/customer/{{name}}", profit_customer_handler)
    r.add_get(f"{_PREFIX}/order/{{thread_id}}", profit_order_handler)
    r.add_post(f"{_PREFIX}/product/{{code}}/cost", profit_cost_update_handler)
    r.add_post(f"{_PREFIX}/products/bulk-update", profit_bulk_update_handler)
    r.add_get(f"{_PREFIX}/api/orders", profit_orders_feed_handler)
    r.add_post(f"{_PREFIX}/api/freeze-costs", profit_freeze_costs_handler)
