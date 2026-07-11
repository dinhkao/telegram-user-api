"""HTTP API bảng lương SP — GET/POST /api/wages. CHỈ văn phòng (tiền lương).

Đơn giá lương / 1 cây theo mã SP, lưu production_wages (production_store.wages).
Sửa xong emit productions_changed → dashboard tiền công + phiếu báo cáo tự tính lại.
Client: webapp/src/pages/WageTable.tsx (#/luong-sp). Đăng ký: app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from production_store.wages import list_wages, set_wage
from server_app.production_wages import office_user


async def wages_list_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được xem bảng lương."}, status=403)

    def _run():
        conn = get_connection()
        try:
            return list_wages(conn)
        finally:
            conn.close()

    wages = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "wages": wages})


async def wages_set_handler(request: web.Request):
    user = office_user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được sửa bảng lương."}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    code = str(body.get("code") or "")
    try:
        luong = float(body.get("luong") or 0)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "đơn giá không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            set_wage(conn, code, luong, by=str(user.get("username") or ""))
            return list_wages(conn)
        finally:
            conn.close()

    try:
        wages = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    # tiền công/báo cáo tính live theo bảng lương → cho các trang tiền refetch
    from server_app.realtime import emit_productions_changed
    emit_productions_changed()
    return web.json_response({"ok": True, "wages": wages})
