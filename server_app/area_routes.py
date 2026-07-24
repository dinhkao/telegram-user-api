"""HTTP KHU VỰC XƯỞNG + BÁO CÁO VỆ SINH — /api/areas (100% local).

GET list (dashboard: khu nào đã/chưa vệ sinh hôm nay) · POST tạo khu vực (mọi user) ·
POST {id} sửa (văn phòng) · DELETE {id} xoá (admin) · GET {id} chi tiết + báo cáo ·
POST {id}/report tạo báo cáo hôm nay (mọi user, ymd tính server) · POST report/{rid}/delete
(admin). Ảnh gắn báo cáo qua media scope 'area_report'. Nối: area_store, entity_media_store,
server_app.realtime, audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import area_store
from area_store import domain
from entity_media_store import image_counts, latest_image_ids, list_images
from utils.db import get_connection

log = logging.getLogger("area_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _conn():
    conn = get_connection()
    area_store.ensure_tables(conn)
    return conn


def _actor_type(request: web.Request) -> str:
    return "web_user" if request.get("web_user") else "http_client"


def _audit(action: str, area_id, actor: str, actor_type: str, payload: dict) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="area", thread_id=area_id, actor_type=actor_type,
        actor_id=actor, source=action, payload=payload))


# ── Dashboard ────────────────────────────────────────────────────────────────
async def areas_all_handler(request: web.Request):
    """GET /api/areas — dashboard: khu vực + trạng thái vệ sinh hôm nay + dải 7 ngày."""
    def _run():
        conn = _conn()
        try:
            today = domain.today_vn()
            areas = area_store.list_areas(conn)
            week_from = domain.last_n_days(today, 7)[0]
            reports = area_store.list_reports_since(conn, week_from)
            # số ảnh mỗi báo cáo (để "reported" chỉ đúng khi ≥1 ảnh)
            counts = image_counts("area_report", [int(r["id"]) for r in reports])
            for r in reports:
                r["photo_count"] = int(counts.get(int(r["id"]), 0))
            rows, done = domain.build_dashboard_rows(areas, reports, today, week=7)
            # thumbnail = ảnh mới nhất của BÁO CÁO GẦN NHẤT mỗi khu vực (reports đã
            # sort mới→cũ nên id đầu tiên gặp = gần nhất).
            latest_map: dict[int, int] = {}
            for r in reports:
                latest_map.setdefault(int(r["area_id"]), int(r["id"]))
            thumbs = latest_image_ids("area_report", list(latest_map.values()))
            for row in rows:
                rid = latest_map.get(row["id"])
                img = thumbs.get(rid) if rid else None
                row["thumb_image_id"] = img
                # report_id chứa ảnh thumb (để webapp dựng URL /api/media/area_report/{rid})
                row["thumb_report_id"] = rid if img else None
            return today, rows, done, len(areas)
        finally:
            conn.close()
    today, rows, done, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "today_ymd": today, "areas": rows,
                              "done_count": done, "total": total})


async def area_detail_handler(request: web.Request):
    """GET /api/areas/{id} — khu vực + báo cáo (mỗi báo cáo kèm images + photo_count)."""
    try:
        aid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _get():
        conn = _conn()
        try:
            area = area_store.get_area(conn, aid)
            if not area:
                return None, None, None
            reports = area_store.list_reports(conn, aid)
            counts = image_counts("area_report", [int(r["id"]) for r in reports])
            for r in reports:
                imgs = list_images("area_report", int(r["id"]))
                r["images"] = [int(i["id"]) for i in imgs]
                r["photo_count"] = int(counts.get(int(r["id"]), len(imgs)))
            return area, reports, domain.today_vn()
        finally:
            conn.close()
    area, reports, today = await asyncio.to_thread(_get)
    if not area:
        return web.json_response({"ok": False, "error": "Không tìm thấy khu vực"}, status=404)
    return web.json_response({"ok": True, "area": area, "reports": reports, "today_ymd": today})


# ── Khu vực CRUD ─────────────────────────────────────────────────────────────
async def area_create_handler(request: web.Request):
    """POST /api/areas — MỌI user đăng nhập được tạo khu vực (quyết định nghiệp vụ)."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    name = str(body.get("name") or "").strip()
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return area_store.add_area(conn, name, note, by=actor)
        finally:
            conn.close()
    area, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)

    from server_app.realtime import emit_area_changed
    emit_area_changed(area["id"])
    _audit("area.created", area["id"], actor, _actor_type(request),
           {"area_id": area["id"], "area_name": area["name"], "note": area.get("note") or ""})
    return web.json_response({"ok": True, "area": area})


async def area_update_handler(request: web.Request):
    """POST /api/areas/{id} — CHỈ văn phòng sửa tên/ghi chú."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa khu vực"}, status=403)
    try:
        aid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    name = body.get("name")
    note = body.get("note")
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return area_store.update_area(
                conn, aid,
                name=str(name) if name is not None else None,
                note=str(note) if note is not None else None,
            )
        finally:
            conn.close()
    area, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)

    from server_app.realtime import emit_area_changed
    emit_area_changed(aid)
    _audit("area.updated", aid, actor, _actor_type(request),
           {"area_id": aid, "area_name": area["name"], "note": area.get("note") or ""})
    return web.json_response({"ok": True, "area": area})


async def area_delete_handler(request: web.Request):
    """DELETE /api/areas/{id} — CHỈ admin, xoá mềm."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá khu vực"}, status=403)
    try:
        aid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            area = area_store.get_area(conn, aid)
            ok, err = area_store.soft_delete_area(conn, aid, by=actor)
            return area, ok, err
        finally:
            conn.close()
    area, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    from server_app.realtime import emit_area_changed
    emit_area_changed(aid)
    _audit("area.deleted", aid, actor, _actor_type(request),
           {"area_id": aid, "area_name": (area or {}).get("name") or ""})
    return web.json_response({"ok": True})


# ── Báo cáo vệ sinh ──────────────────────────────────────────────────────────
async def area_report_handler(request: web.Request):
    """POST /api/areas/{id}/report — MỌI user. ymd = hôm nay (tính SERVER). Idempotent
    theo ngày: đã có báo cáo hôm nay thì trả lại (created=false) để chụp thêm ảnh."""
    try:
        aid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            if not area_store.get_area(conn, aid):
                return None, None, None, "Không tìm thấy khu vực"
            ymd = domain.today_vn()
            rep, created = area_store.get_or_create_report(conn, aid, ymd, by=actor, note=note)
            return rep, created, ymd, None
        finally:
            conn.close()
    rep, created, ymd, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    from server_app.realtime import emit_area_changed
    emit_area_changed(aid)
    if created:
        _audit("area.report_created", aid, actor, _actor_type(request),
               {"area_id": aid, "report_id": rep["id"], "ymd": ymd})
    return web.json_response({"ok": True, "report_id": rep["id"], "ymd": ymd, "created": created})


async def area_report_delete_handler(request: web.Request):
    """POST /api/areas/report/{rid}/delete — CHỈ admin, xoá mềm báo cáo."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá báo cáo"}, status=403)
    try:
        rid = int(request.match_info.get("rid", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            rep = area_store.get_report(conn, rid)
            ok, err = area_store.soft_delete_report(conn, rid, by=actor)
            return rep, ok, err
        finally:
            conn.close()
    rep, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    area_id = int(rep["area_id"]) if rep else None
    from server_app.realtime import emit_area_changed
    emit_area_changed(area_id)
    _audit("area.report_deleted", area_id, actor, _actor_type(request),
           {"area_id": area_id, "report_id": rid, "ymd": (rep or {}).get("ymd")})
    return web.json_response({"ok": True})
