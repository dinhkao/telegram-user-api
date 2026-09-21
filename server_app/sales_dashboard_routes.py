"""API JSON cho dashboard bán hàng native (#/ban-hang), chỉ văn phòng."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH


def _dates(request: web.Request) -> tuple[str, str]:
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    since = (request.query.get("since") or date.fromisoformat(today).replace(day=1).isoformat()).strip()
    until = (request.query.get("until") or today).strip()
    try:
        start, end = date.fromisoformat(since), date.fromisoformat(until)
        if start.isoformat() != since or end.isoformat() != until or start > end:
            raise ValueError
        if (end - start).days >= 3660:
            raise ValueError
    except ValueError:
        raise web.HTTPBadRequest(
            text='{"ok":false,"error":"Khoảng ngày không hợp lệ: ngày bắt đầu phải trước hoặc bằng ngày kết thúc, tối đa 3.660 ngày."}',
            content_type="application/json",
        )
    return since, until


async def sales_dashboard_handler(request: web.Request):
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới xem được báo cáo bán hàng"}, status=403)

    from sales_dashboard.compute import sales_dashboard_data
    since, until = _dates(request)
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()

    def work():
        conn = get_connection(SHARED_DB_PATH)
        try:
            conn.execute("BEGIN")
            return sales_dashboard_data(conn, since, until, today)
        finally:
            conn.close()

    data = await asyncio.to_thread(work)
    return web.json_response({"ok": True, **data})


async def sales_dashboard_today_handler(request: web.Request):
    """KPI gọn cho thẻ báo cáo trên Order Dashboard, vẫn chỉ văn phòng."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới xem được báo cáo bán hàng"}, status=403)

    from sales_dashboard.compute import today_sales_summary
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()

    def work():
        conn = get_connection(SHARED_DB_PATH)
        try:
            conn.execute("BEGIN")
            return today_sales_summary(conn, today)
        finally:
            conn.close()

    data = await asyncio.to_thread(work)
    return web.json_response({"ok": True, **data})


def register(r) -> None:
    r.add_get("/api/sales-dashboard", sales_dashboard_handler)
    r.add_get("/api/sales-dashboard/today", sales_dashboard_today_handler)
