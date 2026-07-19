"""API CHẤM CÔNG. POST /api/attendance/events = ingestion cho collector Windows
(bearer token riêng của máy — KHÔNG phải web token, miễn web_auth ở middleware; batch
idempotent theo event_id, chỉ 2xx sau khi commit). Các GET/map = văn phòng xem punch +
gán mã NV máy → thợ. Nối: attendance_store, server_app.production_wages (office gate).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from aiohttp import web

from server_app.config import ATTENDANCE_BEARER_TOKEN, ATTENDANCE_MACHINE_IDS
from server_app.production_wages import office_user
from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
import attendance_store

log = logging.getLogger("attendance")
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YM = re.compile(r"^\d{4}-\d{2}$")


def _bearer(request: web.Request) -> str:
    auth = request.headers.get("Authorization", "")
    return auth[len("Bearer "):].strip() if auth.startswith("Bearer ") else ""


def _db():
    return get_connection(SHARED_DB_PATH)


async def attendance_ingest_handler(request: web.Request):
    """POST /api/attendance/events — collector gửi batch punch. Trả 2xx CHỈ sau khi
    commit; batch toàn-trùng-lặp vẫn 2xx (retry là bình thường)."""
    if not attendance_store.token_ok(ATTENDANCE_BEARER_TOKEN, _bearer(request)):
        # không log token; chỉ log nguồn để soi lỗi xác thực
        log.warning("attendance auth failed from %s", request.remote)
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    events, err = attendance_store.validate_batch(payload, set(ATTENDANCE_MACHINE_IDS))
    if err:
        log.warning("attendance batch rejected: %s", err)
        return web.json_response({"ok": False, "error": err}, status=422)

    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return attendance_store.insert_events(conn, events)
        finally:
            conn.close()

    result = await asyncio.to_thread(_run)
    log.info("attendance batch: %d new, %d duplicate (machine %s)",
             result["accepted"], result["duplicates"], payload.get("machine_id"))
    return web.json_response({"ok": True, **result})


def _deny(request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    return None


async def attendance_list_handler(request: web.Request):
    """GET /api/attendance/list?day=YYYY-MM-DD[&employee_code=|&worker_id=] — office."""
    d = _deny(request)
    if d:
        return d
    day = (request.query.get("day") or "").strip() or None
    if day and not _YMD.match(day):
        return web.json_response({"ok": False, "error": "day phải dạng YYYY-MM-DD"}, status=400)
    code = (request.query.get("employee_code") or "").strip() or None
    wq = (request.query.get("worker_id") or "").strip()
    worker_id = int(wq) if wq.isdigit() else None

    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return attendance_store.list_events(conn, day=day, employee_code=code,
                                                worker_id=worker_id)
        finally:
            conn.close()

    return web.json_response({"ok": True, "events": await asyncio.to_thread(_run)})


async def attendance_summary_handler(request: web.Request):
    """GET /api/attendance/summary?ym=YYYY-MM — mỗi (ngày, NV): MỌI giờ chấm (times)
    + hàng chờ mã chưa map + last_sync (lúc nhận batch gần nhất — collector 30ph/lần).
    Office."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)

    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return (attendance_store.day_summary(conn, ym),
                    attendance_store.unmapped_codes(conn),
                    attendance_store.last_sync(conn))
        finally:
            conn.close()

    days, unmapped, sync = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "days": days, "unmapped": unmapped,
                              "last_sync": sync, "sync_interval_min": 30})


async def attendance_map_handler(request: web.Request):
    """POST /api/attendance/map {employee_code, worker_id|null} — gán mã máy → thợ,
    backfill event cũ. Office."""
    d = _deny(request)
    if d:
        return d
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    code = str(body.get("employee_code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "error": "thiếu employee_code"}, status=400)
    wid = body.get("worker_id")
    if wid is not None and not isinstance(wid, int):
        return web.json_response({"ok": False, "error": "worker_id phải là số"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return attendance_store.map_employee_code(conn, code, wid, by=by)
        finally:
            conn.close()

    updated = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "updated_events": updated})


async def attendance_map_list_handler(request: web.Request):
    """GET /api/attendance/map — mọi map mã máy → thợ (chi tiết thợ hiện ID chấm công).
    Office."""
    d = _deny(request)
    if d:
        return d

    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return attendance_store.list_mappings(conn)
        finally:
            conn.close()

    return web.json_response({"ok": True, "mappings": await asyncio.to_thread(_run)})


def _office_run(request, fn):
    """Chạy fn(conn) trong thread với schema đảm bảo — dùng cho các handler sửa tay."""
    def _run():
        conn = _db()
        try:
            attendance_store.ensure_schema(conn)
            return fn(conn)
        finally:
            conn.close()
    return asyncio.to_thread(_run)


async def attendance_day_handler(request: web.Request):
    """GET /api/attendance/day?employee_code=&day= — chi tiết 1 (NV, ngày) cho popup
    sửa giờ: giờ máy (kèm cờ ẩn) + giờ thêm tay. Office."""
    d = _deny(request)
    if d:
        return d
    code = (request.query.get("employee_code") or "").strip()
    day = (request.query.get("day") or "").strip()
    if not code or not _YMD.match(day):
        return web.json_response({"ok": False, "error": "cần employee_code + day YYYY-MM-DD"}, status=400)
    detail = await _office_run(request, lambda conn: attendance_store.day_detail(conn, code, day))
    return web.json_response({"ok": True, **detail})


async def attendance_manual_add_handler(request: web.Request):
    """POST /api/attendance/manual {employee_code, day, time} — THÊM giờ chấm tay
    (không đụng dữ liệu máy). Office."""
    d = _deny(request)
    if d:
        return d
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    by = request.get("web_user") or ""
    try:
        mid = await _office_run(request, lambda conn: attendance_store.add_manual(
            conn, str(body.get("employee_code") or ""), str(body.get("day") or ""),
            str(body.get("time") or ""), by=by))
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "id": mid})


async def attendance_manual_delete_handler(request: web.Request):
    """POST /api/attendance/manual/delete {id} — xoá 1 giờ chấm tay. Office."""
    d = _deny(request)
    if d:
        return d
    try:
        body = await request.json()
        mid = int(body.get("id"))
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "thiếu id"}, status=400)
    ok = await _office_run(request, lambda conn: attendance_store.delete_manual(conn, mid))
    if not ok:
        return web.json_response({"ok": False, "error": "không tìm thấy"}, status=404)
    return web.json_response({"ok": True})


async def attendance_suppress_handler(request: web.Request):
    """POST /api/attendance/suppress {event_id, suppressed} — ẩn/hiện 1 giờ chấm MÁY
    (raw giữ nguyên — máy gửi lại không đè). Office."""
    d = _deny(request)
    if d:
        return d
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    eid = str(body.get("event_id") or "").strip()
    on = bool(body.get("suppressed"))
    by = request.get("web_user") or ""
    try:
        await _office_run(request, lambda conn: attendance_store.set_suppressed(conn, eid, on, by=by))
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True})
