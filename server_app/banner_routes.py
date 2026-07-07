"""Bảng tin banner — bình luận được GHIM chạy trên banner webapp trong 24h.

Bảng banner_pins (app.db): text + href (link nguồn #/order/…) + người ghim +
hết hạn. API: GET /api/banner/pins (còn hạn), POST /api/banner/pin {text, href?}
(hết hạn sau 24h), DELETE /api/banner/pin/{id} (admin). Phát realtime
banner_changed để mọi máy cập nhật banner ngay. Đăng ký ở app_factory.
Kết nối: utils.db (app.db), server_app.realtime, server_app.order_api_common.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from utils.db import get_connection, transaction

log = logging.getLogger("server")

PIN_TTL_SEC = 24 * 3600  # bình luận ghim sống 24h


def _ensure(conn) -> None:
    with transaction(conn):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS banner_pins ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, href TEXT DEFAULT '', "
            "created_by TEXT DEFAULT '', created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)"
        )


async def banner_pins_handler(request: web.Request):
    """Danh sách pin CÒN HẠN (mới nhất trước) cho banner."""
    def _run():
        conn = get_connection()
        try:
            _ensure(conn)
            rows = conn.execute(
                "SELECT id, text, href, created_by, created_at, expires_at FROM banner_pins "
                "WHERE expires_at > ? ORDER BY created_at DESC", (int(time.time()),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    pins = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "pins": pins})


async def banner_pin_create_handler(request: web.Request):
    """Ghim 1 dòng lên banner (24h). Body {text, href?}."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    from server_app.order_api_common import apply_web_actor
    apply_web_actor(request, body)
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "Thiếu nội dung"}, status=400)
    href = (body.get("href") or "").strip()
    by = str(body.get("user_id") or "")
    now = int(time.time())

    def _run():
        conn = get_connection()
        try:
            _ensure(conn)
            with transaction(conn):
                cur = conn.execute(
                    "INSERT INTO banner_pins (text, href, created_by, created_at, expires_at) VALUES (?,?,?,?,?)",
                    (text[:200], href[:100], by, now, now + PIN_TTL_SEC),
                )
                return cur.lastrowid
        finally:
            conn.close()
    pin_id = await asyncio.to_thread(_run)
    from server_app.realtime import emit_banner_changed
    emit_banner_changed()
    return web.json_response({"ok": True, "id": pin_id})


async def banner_pin_delete_handler(request: web.Request):
    """Gỡ 1 pin trước hạn — chỉ admin."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được gỡ khỏi bảng tin"}, status=403)
    pin_id = request.match_info.get("pin_id", "")
    if not pin_id.isdigit():
        return web.json_response({"ok": False, "error": "pin_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            _ensure(conn)
            with transaction(conn):
                conn.execute("DELETE FROM banner_pins WHERE id = ?", (int(pin_id),))
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    from server_app.realtime import emit_banner_changed
    emit_banner_changed()
    return web.json_response({"ok": True})
