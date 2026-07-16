"""API phiếu kiểm kho theo vị trí."""
from __future__ import annotations

import asyncio

from aiohttp import web

from audit_log import async_log_event
from inventory_store.stocktakes import (
    complete_stocktake,
    create_or_resume_stocktake,
    create_stocktake_tables,
    get_stocktake,
    list_place_stocktakes,
    resync_stocktake,
    save_stocktake,
    void_stocktake,
)
from server_app.production_routes import _web_actor
from server_app.realtime import emit_inventory_changed
from server_app.stocktake_lock import acquire, held_by, release
from server_app.tasks import spawn_tracked
from utils.db import get_connection


def _int_match(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info.get(key, ""))
    except (TypeError, ValueError):
        return None


def _actor_type(request: web.Request) -> str:
    return "web_user" if request.get("web_user") else "http_client"


async def place_stocktakes_handler(request: web.Request):
    place_id = _int_match(request, "place_id")
    if place_id is None:
        return web.json_response({"ok": False, "error": "Vị trí không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            return list_place_stocktakes(conn, place_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "stocktakes": rows})


async def stocktake_create_handler(request: web.Request):
    place_id = _int_match(request, "place_id")
    if place_id is None:
        return web.json_response({"ok": False, "error": "Vị trí không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)

    def _run():
        conn = get_connection()
        try:
            return create_or_resume_stocktake(conn, place_id, actor=actor)
        finally:
            conn.close()

    slip, resumed = await asyncio.to_thread(_run)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy vị trí kho"}, status=404)
    if not resumed:
        spawn_tracked("audit.stocktake", async_log_event(
            "stocktake.created", scope="place", thread_id=place_id,
            actor_type=_actor_type(request), actor_id=actor, source="inventory",
            payload={"stocktake_id": slip["id"], "box_count": slip["summary"]["box_count"]},
        ))
        emit_inventory_changed()
    return web.json_response({"ok": True, "stocktake": slip, "resumed": resumed})


async def stocktake_detail_handler(request: web.Request):
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            return get_stocktake(conn, stocktake_id)
        finally:
            conn.close()

    slip = await asyncio.to_thread(_run)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    return web.json_response({"ok": True, "stocktake": slip})


async def stocktake_lock_handler(request: web.Request):
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)
    sid = str(body.get("sid") or "")

    def _read():
        conn = get_connection()
        try:
            return get_stocktake(conn, stocktake_id)
        finally:
            conn.close()

    slip = await asyncio.to_thread(_read)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if slip["status"] != "draft":
        return web.json_response({"ok": True, "holder": None, "mine": False, "completed": True})
    mine, holder = acquire(stocktake_id, actor, sid)
    return web.json_response({"ok": True, "holder": holder, "mine": mine, "completed": False})


async def stocktake_unlock_handler(request: web.Request):
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    release(stocktake_id, _web_actor(request, body), str(body.get("sid") or ""))
    return web.json_response({"ok": True})


async def stocktake_save_handler(request: web.Request):
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    counts = body.get("counts")
    if not isinstance(counts, list):
        return web.json_response({"ok": False, "error": "Dữ liệu kiểm đếm không hợp lệ"}, status=400)

    actor = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    mine, holder = held_by(stocktake_id, actor, sid)
    if not mine:
        return web.json_response({"ok": False, "error": f"{holder or 'Người khác'} đang kiểm kho này", "holder": holder}, status=423)

    def _run():
        conn = get_connection()
        try:
            return save_stocktake(conn, stocktake_id, counts, actor=actor, note=body.get("note"))
        finally:
            conn.close()

    slip, err = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if err == "completed":
        return web.json_response({"ok": False, "error": "Phiếu đã hoàn tất, không thể sửa"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": "Số tồn thực tế phải là số không âm"}, status=400)
    return web.json_response({"ok": True, "stocktake": slip})


async def stocktake_complete_handler(request: web.Request):
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    mine, holder = held_by(stocktake_id, actor, sid)
    if not mine:
        return web.json_response({"ok": False, "error": f"{holder or 'Người khác'} đang kiểm kho này", "holder": holder}, status=423)

    def _run():
        conn = get_connection()
        try:
            return complete_stocktake(conn, stocktake_id, actor=actor, note=body.get("note"))
        finally:
            conn.close()

    slip, err = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if err == "incomplete":
        return web.json_response({"ok": False, "error": "Cần kiểm đủ số tồn thực tế của mọi thùng"}, status=400)
    if err == "stale":
        return web.json_response({
            "ok": False,
            "error": "Kho đã biến động sau khi tạo phiếu — cập nhật lại phiếu trước khi hoàn tất",
            "stale": True, "stocktake": slip,
        }, status=409)
    if err:
        return web.json_response({"ok": False, "error": "Không thể hoàn tất phiếu"}, status=400)
    spawn_tracked("audit.stocktake", async_log_event(
        "stocktake.completed", scope="place", thread_id=slip["place_id"],
        actor_type=_actor_type(request), actor_id=actor, source="inventory",
        payload={"stocktake_id": slip["id"], **slip["summary"]},
    ))
    release(stocktake_id, force=True)
    emit_inventory_changed()
    return web.json_response({"ok": True, "stocktake": slip})


async def stocktake_resync_handler(request: web.Request):
    """Cập nhật lại số sổ sách của phiếu theo tồn hiện tại (gỡ cờ lỗi thời). Cần giữ khoá."""
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    mine, holder = held_by(stocktake_id, actor, sid)
    if not mine:
        return web.json_response({"ok": False, "error": f"{holder or 'Người khác'} đang kiểm kho này", "holder": holder}, status=423)

    def _run():
        conn = get_connection()
        try:
            return resync_stocktake(conn, stocktake_id, actor=actor)
        finally:
            conn.close()

    slip, err = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if err == "completed":
        return web.json_response({"ok": False, "error": "Phiếu đã hoàn tất/huỷ, không thể cập nhật"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": "Không thể cập nhật phiếu"}, status=400)
    spawn_tracked("audit.stocktake", async_log_event(
        "stocktake.resynced", scope="place", thread_id=slip["place_id"],
        actor_type=_actor_type(request), actor_id=actor, source="inventory",
        payload={"stocktake_id": slip["id"], "box_count": slip["summary"]["box_count"]},
    ))
    emit_inventory_changed()
    return web.json_response({"ok": True, "stocktake": slip})


async def stocktake_apply_handler(request: web.Request):
    """ÁP DỤNG chênh lệch kiểm kho vào kho (văn phòng) — tạo phiếu điều chỉnh cho
    từng thùng lệch. Chỉ phiếu ĐÃ CHỐT, 1 lần/phiếu, all-or-nothing (xem
    inventory_store/stocktake_apply.py)."""
    from server_app.order_api_common import is_office_request
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được áp dụng kiểm kho vào kho"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)

    def _run():
        from inventory_store.stocktake_apply import apply_stocktake
        from server_app.inventory_audit import box_snapshot
        conn = get_connection()
        try:
            slip, err = apply_stocktake(conn, stocktake_id, actor=actor)
            snaps = {}   # box_id → snapshot SAU điều chỉnh (event kho cho timeline)
            if slip:
                for a in (slip.get("applied_result") or {}).get("adjusted") or []:
                    s = box_snapshot(conn, a.get("box_id"))
                    if s:
                        snaps[a.get("box_id")] = s
            return slip, err, snaps
        finally:
            conn.close()

    slip, err, snaps = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if err == "not_completed":
        return web.json_response({"ok": False, "error": "Phiếu chưa chốt — hoàn tất kiểm kho trước rồi mới áp dụng"}, status=409)
    if err == "already":
        return web.json_response({"ok": False, "error": "Phiếu này đã áp dụng vào kho rồi"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": err}, status=409)   # thùng cụ thể không áp được
    applied = (slip.get("applied_result") or {}).get("adjusted") or []
    spawn_tracked("audit.stocktake", async_log_event(
        "stocktake.applied", scope="place", thread_id=slip["place_id"],
        actor_type=_actor_type(request), actor_id=actor, source="inventory",
        payload={"stocktake_id": slip["id"], "adjusted": len(applied),
                 "boxes": [{"box_code": a["box_code"], "delta": a["delta"]} for a in applied]},
    ))
    emit_inventory_changed()
    from server_app.realtime import emit_box_changed
    from server_app.inventory_audit import log_box_adjustment
    reason = f"Kiểm kho {slip.get('place_name') or ''} — phiếu #{slip['id']}".strip()
    for a in applied:
        emit_box_changed(a.get("box_id"))
        snap = snaps.get(a.get("box_id"))
        if snap:   # event kho scope box/place → timeline thùng/SP/vị trí thấy điều chỉnh
            log_box_adjustment("adjustment.created", snap, adjustment_id=a.get("adjustment_id"),
                               delta=a.get("delta"), reason=reason, actor=actor,
                               actor_type=_actor_type(request))
    return web.json_response({"ok": True, "stocktake": slip})


async def stocktake_void_handler(request: web.Request):
    """Huỷ phiếu kiểm kho nháp — văn phòng. Giải phóng vị trí cho phiếu mới."""
    from server_app.order_api_common import is_office_request
    stocktake_id = _int_match(request, "stocktake_id")
    if stocktake_id is None:
        return web.json_response({"ok": False, "error": "Phiếu không hợp lệ"}, status=400)
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được huỷ phiếu kiểm kho"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _web_actor(request, body)

    def _run():
        conn = get_connection()
        try:
            return void_stocktake(conn, stocktake_id, actor=actor)
        finally:
            conn.close()

    slip, err = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm kho"}, status=404)
    if err == "completed":
        return web.json_response({"ok": False, "error": "Phiếu đã hoàn tất, không thể huỷ"}, status=409)
    if err:
        return web.json_response({"ok": False, "error": "Không thể huỷ phiếu"}, status=400)
    release(stocktake_id, force=True)
    spawn_tracked("audit.stocktake", async_log_event(
        "stocktake.voided", scope="place", thread_id=slip["place_id"],
        actor_type=_actor_type(request), actor_id=actor, source="inventory",
        payload={"stocktake_id": slip["id"]},
    ))
    emit_inventory_changed()
    return web.json_response({"ok": True, "stocktake": slip})


def ensure_stocktake_schema(conn) -> None:
    create_stocktake_tables(conn)
