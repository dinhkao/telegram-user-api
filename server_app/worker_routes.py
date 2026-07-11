"""HTTP API danh sách thợ (production_workers) — /api/workers[/{id}].
Dùng cho picker tên thợ + template báo cáo mặc định ở trang sửa báo cáo phiếu SX.
Nối: worker_store (CRUD), utils.db. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from worker_store import add_worker, delete_worker, ensure_table, list_workers, reorder_workers, update_worker


def _emit_workers() -> None:
    from server_app.realtime import emit_workers_changed
    emit_workers_changed()


def _conn():
    return get_connection()


async def workers_list_handler(request: web.Request):
    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            workers = list_workers(conn)
        finally:
            conn.close()
        return workers

    workers = await asyncio.to_thread(_run)
    defaults = [w["name"] for w in workers if w["is_default"]]
    return web.json_response({"ok": True, "workers": workers, "defaults": defaults})


async def workers_add_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    name = str(body.get("name") or "")
    is_default = bool(body.get("is_default"))

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            return add_worker(conn, name, is_default)
        finally:
            conn.close()

    try:
        worker = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    _emit_workers()
    return web.json_response({"ok": True, "worker": worker})


async def workers_update_handler(request: web.Request):
    try:
        worker_id = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    name = body.get("name")
    is_default = body.get("is_default")
    weekly_salary = body.get("weekly_salary")

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            return update_worker(
                conn, worker_id,
                name=None if name is None else str(name),
                is_default=None if is_default is None else bool(is_default),
                weekly_salary=None if weekly_salary is None else bool(weekly_salary),
            )
        finally:
            conn.close()

    try:
        worker = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    if worker is None:
        return web.json_response({"ok": False, "error": "không tìm thấy thợ"}, status=404)
    _emit_workers()
    if name is not None:
        # đổi tên cascade vào báo cáo các phiếu → card/dashboard SX cần refresh
        from server_app.realtime import emit_productions_changed
        emit_productions_changed()
    return web.json_response({"ok": True, "worker": worker})


async def workers_reorder_handler(request: web.Request):
    """POST /api/workers/reorder {ids:[...]} — đặt lại sort_order theo thứ tự ids.
    Trả về danh sách thợ + defaults MỚI (đã sắp lại) như /api/workers."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    raw = body.get("ids") or []
    try:
        ids = [int(x) for x in raw]
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "ids không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            reorder_workers(conn, ids)
            return list_workers(conn)
        finally:
            conn.close()

    workers = await asyncio.to_thread(_run)
    defaults = [w["name"] for w in workers if w["is_default"]]
    _emit_workers()
    return web.json_response({"ok": True, "workers": workers, "defaults": defaults})


async def workers_delete_handler(request: web.Request):
    try:
        worker_id = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            ensure_table(conn)
            return delete_worker(conn, worker_id)
        finally:
            conn.close()

    ok = await asyncio.to_thread(_run)
    if not ok:
        return web.json_response({"ok": False, "error": "không tìm thấy thợ"}, status=404)
    _emit_workers()
    return web.json_response({"ok": True})
