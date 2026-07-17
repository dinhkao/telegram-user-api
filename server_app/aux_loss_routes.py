"""API dashboard HAO HỤT NGUYÊN LIỆU PHỤ — GET /api/inventory/aux-loss?limit=.

So NL phụ 'dùng cho sản xuất' (công thức) vs 'sụt giảm thực' (2 lần kiểm kho liên
tiếp của kho nguyên liệu đang dùng). CHỈ VĂN PHÒNG (số liệu hao hụt nhạy cảm).
Nguồn: inventory_store.aux_loss.aux_loss_periods. Client: webapp/src/pages/AuxLoss.tsx.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from inventory_store.aux_loss import aux_loss_periods


async def aux_loss_handler(request: web.Request):
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    try:
        limit = max(1, min(int(request.query.get("limit") or 30), 90))
    except (TypeError, ValueError):
        limit = 30

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return aux_loss_periods(conn, limit=limit)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})
