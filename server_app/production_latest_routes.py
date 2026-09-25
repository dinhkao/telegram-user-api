"""GET /api/production/latest-sp — mã SP của phiếu SẢN XUẤT mới nhất (bỏ phiếu đóng gói,
bỏ phiếu chưa chọn SP) cho tag trên ô "SX" thanh dưới webapp. Đọc production_slips +
products (mã HIỆN HÀNH theo product_id, fallback sp_name snapshot)."""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection

_SQL = (
    "SELECT s.thread_id, COALESCE(pr.code, s.sp_name) AS code FROM production_slips s "
    "LEFT JOIN products pr ON pr.id = s.product_id "
    "WHERE (s.kind IS NULL OR s.kind = '' OR s.kind = 'san_xuat') "
    "AND TRIM(COALESCE(pr.code, s.sp_name, '')) != '' "
    "ORDER BY s.date_code DESC, s.thread_id DESC LIMIT 1"
)


async def production_latest_sp_handler(request: web.Request):
    def _run():
        conn = _get_connection()
        try:
            row = conn.execute(_SQL).fetchone()
            return {"code": str(row[1]).strip(), "thread_id": row[0]} if row else None
        except Exception:  # noqa: BLE001 — chưa có bảng phiếu SX (DB lẻ/test)
            return None
        finally:
            conn.close()

    return web.json_response({"ok": True, "latest": await asyncio.to_thread(_run)})
