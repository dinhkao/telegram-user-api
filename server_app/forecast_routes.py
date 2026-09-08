"""HTTP DỰ BÁO HÀNG HOÁ HẰNG NGÀY — /api/forecasts (100% local, app.db).

GET list (mới nhất trước, `viewed` theo user) · GET today (popup "chưa xem") · GET {id}
(chi tiết + TỰ đánh dấu đã xem) · GET compute?ymd= (văn phòng — chạy engine live để soi số)
· POST publish (CHỈ loopback: job 7h sáng `tools/forecast_publish.py` đăng bản mới → realtime
`forecast_changed` + chuông/FCM route `#/du-bao/<id>`, chỉ báo 1 lần/ngày).
Nối: forecast_store, server_app.notify, server_app.realtime, web_auth.middleware.effective_remote.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiohttp import web

import forecast_store
from server_app.web_auth.middleware import effective_remote
from utils.daily_photo_report import today_vn
from utils.db import get_connection

log = logging.getLogger("forecast_routes")
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _username(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("username") or "")
    return str(u or "")


def _conn():
    conn = get_connection()
    forecast_store.ensure_tables(conn)
    return conn


async def forecasts_list_handler(request: web.Request):
    user = _username(request)
    try:
        limit = int(request.query.get("limit") or 30)
    except ValueError:
        limit = 30
    before = request.query.get("before")
    before_id = int(before) if before and before.isdigit() else None

    def _w():
        conn = _conn()
        try:
            return forecast_store.list_forecasts(conn, limit=limit, before_id=before_id, username=user)
        finally:
            conn.close()

    items, more = await asyncio.to_thread(_w)
    return web.json_response({"items": items, "has_more": more})


async def forecast_today_handler(request: web.Request):
    user = _username(request)
    ymd = today_vn()

    def _w():
        conn = _conn()
        try:
            row = forecast_store.get_by_ymd(conn, ymd)
            if not row:
                return None, False
            v = forecast_store.viewed_by(conn, row["id"], user)
            row["viewed"] = v
            return row, v
        finally:
            conn.close()

    row, viewed = await asyncio.to_thread(_w)
    return web.json_response({"ymd": ymd, "forecast": row, "viewed": viewed})


async def forecast_detail_handler(request: web.Request):
    try:
        fid = int(request.match_info["id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "id không hợp lệ"}, status=400)
    user = _username(request)

    def _w():
        conn = _conn()
        try:
            row = forecast_store.get_forecast(conn, fid, full=True)
            if row and user:
                forecast_store.mark_viewed(conn, fid, user)
            if row:
                row["viewed"] = True
            return row
        finally:
            conn.close()

    row = await asyncio.to_thread(_w)
    if not row:
        return web.json_response({"error": "Không có bản dự báo này"}, status=404)
    return web.json_response(row)


async def forecast_compute_handler(request: web.Request):
    """Chạy engine live (văn phòng) — soi số liệu trước khi đăng / debug."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"error": "Chỉ văn phòng"}, status=403)
    ymd = request.query.get("ymd") or today_vn()
    try:
        today = dt.date.fromisoformat(ymd)
    except ValueError:
        return web.json_response({"error": "ymd không hợp lệ"}, status=400)

    def _w():
        from forecast_store.engine import compute
        from forecast_store.history import load_lines
        conn = _conn()
        try:
            prev = forecast_store.get_by_ymd(conn, (today - dt.timedelta(days=1)).isoformat())
            lines = load_lines(conn, today - dt.timedelta(days=420))
            return compute(lines, today, prev["day_total"] if prev else None)
        finally:
            conn.close()

    return web.json_response(await asyncio.to_thread(_w))


async def forecast_publish_handler(request: web.Request):
    """Đăng bản dự báo — CHỈ từ chính máy chủ (job cron). Qua Funnel mọi request là
    127.0.0.1 nên phải soi IP thật (X-Forwarded-For) — xem web_auth.middleware."""
    remote = effective_remote(request.remote, request.headers)
    if remote not in _LOOPBACK:
        return web.json_response({"error": "forbidden"}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"error": "JSON không hợp lệ"}, status=400)
    if not isinstance(body, dict) or not body.get("ymd"):
        return web.json_response({"error": "thiếu ymd"}, status=400)

    def _w():
        conn = _conn()
        try:
            return forecast_store.upsert_forecast(
                conn, ymd=str(body["ymd"]), title=str(body.get("title") or ""),
                summary=str(body.get("summary") or ""), body_md=str(body.get("body_md") or ""),
                data=body.get("data") if isinstance(body.get("data"), dict) else {},
                model=str(body.get("model") or "auto"), by=str(body.get("by") or "cron"))
        finally:
            conn.close()

    try:
        row, created = await asyncio.to_thread(_w)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    from server_app.realtime import emit_forecast_changed
    emit_forecast_changed(row["id"])
    # Chuông + FCM: 1 lần/ngày (bản đầu tiên của ngày, hoặc ép notify=true khi bản
    # tự động được agent thay bằng bản có nhận định).
    if created or body.get("notify") is True:
        from server_app.notify import push_bg
        summary = str(row.get("summary") or "")
        push_bg("📈 " + row["title"], "\n".join(summary.splitlines()[:2]),
                {"type": "forecast", "route": f"#/du-bao/{row['id']}"})
    log.info("forecast published ymd=%s id=%s created=%s model=%s", row["ymd"], row["id"], created, row["model"])
    return web.json_response({"ok": True, "id": row["id"], "created": created})


def register(r: web.UrlDispatcher) -> None:
    r.add_get("/api/forecasts", forecasts_list_handler)
    r.add_get("/api/forecasts/today", forecast_today_handler)
    r.add_get("/api/forecasts/compute", forecast_compute_handler)   # văn phòng
    r.add_post("/api/forecasts/publish", forecast_publish_handler)  # loopback (cron)
    r.add_get("/api/forecasts/{id}", forecast_detail_handler)
