"""HTTP BÁO CÁO CHẤT LƯỢNG MÂM KẸO — /api/quality (100% local).

GET list (dashboard: thợ nào đã/chưa chụp mâm hôm nay) · GET {worker_id} chi tiết
thợ + báo cáo · POST {worker_id}/report tạo báo cáo hôm nay (mọi user, ymd tính
SERVER) · POST report/{rid}/delete (admin). Thợ lấy từ `production_workers`
(worker_store) — trang này KHÔNG tạo/sửa/xoá thợ, việc đó ở #/tho. Ảnh gắn báo cáo
qua media scope 'quality_report'. Nối: quality_store, worker_store,
entity_media_store, server_app.realtime, audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import quality_store
import worker_store
from entity_media_store import image_counts, latest_image_ids
from quality_store import domain
from server_app.photo_report_view import attach_today_scores, enrich_reports
from utils.db import get_connection

log = logging.getLogger("quality_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _conn():
    conn = get_connection()
    quality_store.ensure_tables(conn)
    worker_store.ensure_table(conn)
    return conn


def _actor_type(request: web.Request) -> str:
    return "web_user" if request.get("web_user") else "http_client"


def _audit(action: str, worker_id, actor: str, actor_type: str, payload: dict) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="quality", thread_id=worker_id, actor_type=actor_type,
        actor_id=actor, source=action, payload=payload))


def _worker(conn, worker_id: int) -> dict | None:
    """1 thợ theo id (danh sách thợ nhỏ — lọc trong Python, khỏi thêm API store)."""
    for w in worker_store.list_workers(conn):
        if int(w["id"]) == int(worker_id):
            return w
    return None


# ── Dashboard ────────────────────────────────────────────────────────────────
async def quality_all_handler(request: web.Request):
    """GET /api/quality — dashboard: thợ + trạng thái chụp mâm hôm nay + dải 7 ngày."""
    def _run():
        conn = _conn()
        try:
            today = domain.today_vn()
            # ghi chú hồ sơ thợ là chuyện văn phòng → KHÔNG đẩy ra bảng chung
            workers = [{"id": w["id"], "name": w["name"], "note": ""}
                       for w in worker_store.list_workers(conn)]
            week_from = domain.last_n_days(today, 7)[0]
            reports = quality_store.list_reports_since(conn, week_from)
            # số ảnh mỗi báo cáo (để "reported" chỉ đúng khi ≥1 ảnh)
            counts = image_counts("quality_report", [int(r["id"]) for r in reports])
            for r in reports:
                r["photo_count"] = int(counts.get(int(r["id"]), 0))
            rows, done = domain.build_dashboard_rows(workers, reports, today, week=7)
            # điểm TB mâm hôm nay của từng thợ (chấm điểm 0–10 trên từng ảnh)
            attach_today_scores("quality_report", rows,
                                {int(r["worker_id"]): int(r["id"]) for r in reports
                                 if str(r.get("ymd")) == today})
            # thumbnail = ảnh mới nhất của BÁO CÁO GẦN NHẤT mỗi thợ (reports đã sort
            # mới→cũ nên id đầu tiên gặp = gần nhất).
            latest_map: dict[int, int] = {}
            for r in reports:
                latest_map.setdefault(int(r["worker_id"]), int(r["id"]))
            thumbs = latest_image_ids("quality_report", list(latest_map.values()))
            for row in rows:
                rid = latest_map.get(row["id"])
                img = thumbs.get(rid) if rid else None
                row["thumb_image_id"] = img
                # report_id chứa ảnh thumb (webapp dựng URL /api/media/quality_report/{rid})
                row["thumb_report_id"] = rid if img else None
            return today, rows, done, len(workers)
        finally:
            conn.close()
    today, rows, done, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "today_ymd": today, "workers": rows,
                              "done_count": done, "total": total})


async def quality_worker_handler(request: web.Request):
    """GET /api/quality/{id} — thợ + báo cáo (mỗi báo cáo kèm images + photo_count)."""
    try:
        wid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _get():
        conn = _conn()
        try:
            worker = _worker(conn, wid)
            if not worker:
                return None, None, None
            reports = quality_store.list_reports(conn, wid)
            # ảnh + điểm 0–10 + số bình luận (từng ảnh và cả ngày)
            enrich_reports("quality_report", "quality_image", reports)
            return worker, reports, domain.today_vn()
        finally:
            conn.close()
    worker, reports, today = await asyncio.to_thread(_get)
    if not worker:
        return web.json_response({"ok": False, "error": "Không tìm thấy thợ"}, status=404)
    return web.json_response({
        "ok": True,
        "worker": {"id": worker["id"], "name": worker["name"]},
        "reports": reports, "today_ymd": today,
    })


# ── Báo cáo chất lượng ───────────────────────────────────────────────────────
async def quality_report_handler(request: web.Request):
    """POST /api/quality/{id}/report — MỌI user. ymd = hôm nay (tính SERVER). Idempotent
    theo ngày: đã có báo cáo hôm nay thì trả lại (created=false) để chụp thêm mâm."""
    try:
        wid = int(request.match_info.get("id", ""))
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
            worker = _worker(conn, wid)
            if not worker:
                return None, None, None, None, "Không tìm thấy thợ"
            ymd = domain.today_vn()
            rep, created = quality_store.get_or_create_report(conn, wid, ymd, by=actor, note=note)
            return rep, created, ymd, worker, None
        finally:
            conn.close()
    rep, created, ymd, worker, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    from server_app.realtime import emit_quality_changed
    emit_quality_changed(wid)
    if created:
        _audit("quality.report_created", wid, actor, _actor_type(request),
               {"worker_id": wid, "worker_name": (worker or {}).get("name") or "",
                "report_id": rep["id"], "ymd": ymd})
    return web.json_response({"ok": True, "report_id": rep["id"], "ymd": ymd, "created": created})


async def quality_report_delete_handler(request: web.Request):
    """POST /api/quality/report/{rid}/delete — CHỈ admin, xoá mềm báo cáo."""
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
            rep = quality_store.get_report(conn, rid)
            worker = _worker(conn, int(rep["worker_id"])) if rep else None
            ok, err = quality_store.soft_delete_report(conn, rid, by=actor)
            return rep, worker, ok, err
        finally:
            conn.close()
    rep, worker, ok, err = await asyncio.to_thread(_del)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)

    worker_id = int(rep["worker_id"]) if rep else None
    from server_app.realtime import emit_quality_changed
    emit_quality_changed(worker_id)
    _audit("quality.report_deleted", worker_id, actor, _actor_type(request),
           {"worker_id": worker_id, "worker_name": (worker or {}).get("name") or "",
            "report_id": rid, "ymd": (rep or {}).get("ymd")})
    return web.json_response({"ok": True})
