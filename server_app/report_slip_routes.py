"""HTTP API phiếu báo cáo sản xuất — /api/report-slips[/{id}].

NHẠY CẢM (tiền lương): mọi endpoint CHỈ văn phòng (admin/van_phong — chặn qua
production_wages.office_user); xoá = admin. Nội dung báo cáo tính live từ
production_store.report_slips.compute_range_report. Client:
webapp/src/pages/ReportSlips.tsx + ReportSlipDetail.tsx. Đăng ký: app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from production_store.report_slips import (
    add_slip, compute_range_report, delete_slip, ensure_table, get_slip, list_slips,
)
from server_app.production_wages import office_user


def _conn():
    return get_connection(SHARED_DB_PATH)


def _emit():
    from server_app.realtime import emit_report_slips_changed
    emit_report_slips_changed()


async def report_slips_list_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được xem báo cáo."}, status=403)

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            slips = list_slips(conn)
            # đính kèm tổng cộng (SP + tiền) từng phiếu báo cáo cho danh sách
            for s in slips:
                rep = compute_range_report(conn, s["from_ymd"], s["to_ymd"])
                s["totals"] = rep["totals"]
                s["worker_count"] = len(rep["workers"])
                s["phieu_count"] = len(rep["phieus"])
            return slips
        finally:
            conn.close()

    slips = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "slips": slips})


async def report_slips_create_handler(request: web.Request):
    user = office_user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được tạo báo cáo."}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            return add_slip(
                conn,
                str(body.get("from") or ""), str(body.get("to") or ""),
                note=str(body.get("note") or ""), by=str(user.get("username") or ""),
            )
        finally:
            conn.close()

    try:
        slip = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    _emit()
    return web.json_response({"ok": True, "slip": slip})


async def report_slip_detail_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được xem báo cáo."}, status=403)
    try:
        slip_id = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            slip = get_slip(conn, slip_id)
            if not slip:
                return None
            slip["report"] = compute_range_report(conn, slip["from_ymd"], slip["to_ymd"])
            return slip
        finally:
            conn.close()

    slip = await asyncio.to_thread(_run)
    if slip is None:
        return web.json_response({"ok": False, "error": "không tìm thấy phiếu báo cáo"}, status=404)
    return web.json_response({"ok": True, "slip": slip})


async def report_slip_delete_handler(request: web.Request):
    user = office_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"ok": False, "error": "Chỉ admin được xoá phiếu báo cáo."}, status=403)
    try:
        slip_id = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            return delete_slip(conn, slip_id)
        finally:
            conn.close()

    ok = await asyncio.to_thread(_run)
    if not ok:
        return web.json_response({"ok": False, "error": "không tìm thấy phiếu báo cáo"}, status=404)
    _emit()
    return web.json_response({"ok": True})
