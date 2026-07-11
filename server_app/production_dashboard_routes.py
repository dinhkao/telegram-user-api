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
from production_store.report_rows import dashboard, worker_detail


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


async def production_worker_report_handler(request: web.Request):
    """Chi tiết 1 thợ — mỗi ngày làm phiếu nào / SP gì / bao nhiêu. TIỀN CÔNG (mỗi phiếu +
    tổng) CHỈ đính kèm khi người xem là VĂN PHÒNG (lương nhạy cảm)."""
    name = (request.match_info.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "thiếu tên thợ"}, status=400)
    dfrom = (request.query.get("from") or "").strip() or None
    dto = (request.query.get("to") or "").strip() or None
    username = request.get("web_user")   # do web_auth middleware giải (đọc DB role ở thread)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            data = worker_detail(conn, name, dfrom, dto)
        finally:
            conn.close()
        # Tiền công: chỉ văn phòng — mỗi row (= 1 phiếu) money = tong_calc × đơn giá SP.
        from server_app.production_wages import is_office_username
        if is_office_username(username):
            from production_store.wages import wage_per_cay
            total_money = 0
            for r in data.get("rows", []):
                w = wage_per_cay(r.get("product_code"))
                m = round((r.get("tong_calc") or 0) * w)
                r["money"] = m
                r["wage"] = w
                total_money += m
            data["total_money"] = total_money
            data["can_money"] = True
        else:
            data["can_money"] = False
        return data

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})
