"""API BẢNG LƯƠNG THÁNG — CHỈ VĂN PHÒNG. Xem bảng lương 1 tháng (mọi thợ), sửa phụ
cấp/thưởng theo tháng, ghi nhận/VÔ HIỆU ứng lương + phụ cấp (không xoá — giữ dòng kèm
ai/lúc nào/lý do). Nối: salary_store +
server_app.production_wages (office gate). Client: webapp/src/pages/MonthlyPayroll.tsx.
"""
from __future__ import annotations

import asyncio
import re

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from server_app.production_wages import office_user
import salary_store

_YM = re.compile(r"^\d{4}-\d{2}$")


def _deny(request):
    """None nếu là văn phòng; Response 403 nếu không."""
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    return None


async def payroll_month_handler(request: web.Request):
    """GET /api/payroll/month?ym=YYYY-MM → bảng lương tháng (mọi thợ + tổng)."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})


async def payroll_advances_handler(request: web.Request):
    """GET /api/payroll/advances?ym=YYYY-MM[&worker_id=] → các lần ứng. Không có
    worker_id = MỌI thợ trong tháng (cho trang nhập ứng lương)."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    wq = request.query.get("worker_id")
    worker_id = None
    if wq not in (None, ""):
        try:
            worker_id = int(wq)
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return salary_store.list_advances(conn, ym, worker_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "advances": rows})


async def payroll_adjust_handler(request: web.Request):
    """POST /api/payroll/adjust {ym, worker_id, thuong?, note?, weekly?} — sửa
    thưởng/ghi chú/nhận-lương-tuần theo tháng (field vắng = giữ nguyên). Phụ cấp =
    nhiều khoản, dùng /api/payroll/allowance."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.set_month_adjust(
                conn, ym, worker_id,
                thuong=body.get("thuong"), note=body.get("note"),
                weekly=body.get("weekly"), by=by,
            )
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})


async def payroll_advance_add_handler(request: web.Request):
    """POST /api/payroll/advance {worker_id, ym, amount, adv_date?, note?} — thêm 1 lần ứng."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
        amount = float(body.get("amount"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.add_advance(conn, worker_id, ym, amount,
                                     adv_date=str(body.get("adv_date") or ""),
                                     note=str(body.get("note") or ""), by=by)
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    try:
        data = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, **data})


async def payroll_advance_void_handler(request: web.Request):
    """POST /api/payroll/advance/{id}/void {ym, reason} — VÔ HIỆU 1 lần ứng (không xoá,
    giữ dòng kèm ai/lúc nào/lý do; trả bảng tháng mới)."""
    d = _deny(request)
    if d:
        return d
    try:
        aid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return web.json_response({"ok": False, "error": "Phải nhập lý do vô hiệu"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            ok = salary_store.void_advance(conn, aid, reason, by=by)
            data = salary_store.compute_month_payroll(conn, ym) if _YM.match(ym) else {}
            return ok, data
        finally:
            conn.close()

    ok, data = await asyncio.to_thread(_run)
    return web.json_response({"ok": ok, **data})


async def payroll_allowances_handler(request: web.Request):
    """GET /api/payroll/allowances?ym=YYYY-MM[&worker_id=] → các khoản phụ cấp."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    wq = request.query.get("worker_id")
    worker_id = None
    if wq not in (None, ""):
        try:
            worker_id = int(wq)
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return salary_store.list_allowances(conn, ym, worker_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allowances": rows})


async def payroll_allowance_add_handler(request: web.Request):
    """POST /api/payroll/allowance {worker_id, ym, amount, note?} — thêm 1 khoản phụ cấp."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
        amount = float(body.get("amount"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.add_allowance(conn, worker_id, ym, amount, note=str(body.get("note") or ""), by=by)
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    try:
        data = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, **data})


async def payroll_allowance_void_handler(request: web.Request):
    """POST /api/payroll/allowance/{id}/void {ym, reason} — VÔ HIỆU 1 khoản phụ cấp
    (không xoá, giữ dòng kèm ai/lúc nào/lý do)."""
    d = _deny(request)
    if d:
        return d
    try:
        aid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return web.json_response({"ok": False, "error": "Phải nhập lý do vô hiệu"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            ok = salary_store.void_allowance(conn, aid, reason, by=by)
            data = salary_store.compute_month_payroll(conn, ym) if _YM.match(ym) else {}
            return ok, data
        finally:
            conn.close()

    ok, data = await asyncio.to_thread(_run)
    return web.json_response({"ok": ok, **data})
