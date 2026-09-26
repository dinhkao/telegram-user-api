"""Bật/tắt TĂNG CA của 1 (phiếu SX, thợ) — POST /api/production/{thread_id}/overtime.

CHỈ văn phòng (tiền lương). Mặc định mọi dòng được tính tăng ca theo giờ phiếu
(production_store/overtime.py); tắt = ghi cờ vào production_ot_off. Emit realtime để khối
tiền phiếu + bảng lương/báo cáo tải lại. Nối: production_store.overtime_off,
server_app.production_wages (office_user), server_app.realtime.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection
from server_app.production_wages import office_user


async def set_overtime_handler(request: web.Request):
    """Bật/tắt TĂNG CA của 1 (phiếu, thợ) — CHỈ văn phòng. Body {worker_name, on}."""
    user = office_user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    try:
        tid = int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    body = await request.json()
    worker = str(body.get("worker_name") or "").strip()
    if not worker:
        return web.json_response({"ok": False, "error": "thiếu tên thợ"}, status=400)
    on = bool(body.get("on"))

    def _run():
        from production_store.overtime_off import set_ot_enabled
        conn = _get_connection()
        try:
            set_ot_enabled(conn, tid, worker, on, by=str(user.get("username") or ""))
            # mốc phụ cấp auto = tiền SP SAU tăng ca → bật/tắt TC là tính lại phụ cấp auto
            try:
                from production_store.allowance_auto import reapply_slip
                reapply_slip(conn, tid)
            except Exception:  # noqa: BLE001 — phụ, không chặn thao tác bật/tắt
                pass
        finally:
            conn.close()

    await asyncio.to_thread(_run)
    # tiền phiếu đổi → khối tiền phiếu + bảng lương/báo cáo tải lại
    from server_app.realtime import emit_production_changed, emit_productions_changed
    emit_production_changed(tid)
    emit_productions_changed()
    return web.json_response({"ok": True, "worker_name": worker, "on": on})
