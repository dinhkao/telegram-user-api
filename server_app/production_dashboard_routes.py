"""API dashboard báo cáo sản xuất — GET /api/production/report-dashboard?from=&to=.

Tổng hợp từ bảng quan hệ production_report_rows (production_store.report_rows.dashboard):
tổng sản lượng, theo thợ, theo ngày, theo sản phẩm. from/to = YYYY-MM-DD (lọc report_ymd).
Client: webapp/src/pages/ProductionDashboard.tsx.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from production_store.report_rows import dashboard


async def production_report_dashboard_handler(request: web.Request):
    dfrom = (request.query.get("from") or "").strip() or None
    dto = (request.query.get("to") or "").strip() or None

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return dashboard(conn, dfrom, dto)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})
