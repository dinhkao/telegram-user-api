"""HTTP quy cách đóng gói — GET/POST /api/quy-cach (đọc: mọi user; ghi: admin).

Số cái / 1 thùng, 1 bịch (base + override theo mã SP) + lốc DM180. Lưu ở
settings_store['parse_quy_cach']; parser hoá đơn (order_store.free_text) đọc qua
order_store.quy_cach.load_quy_cach (cache). Đăng ký ở app_factory.
Nối: order_store.quy_cach, settings_store, server_app.order_api_common (is_admin_request), audit_log.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_store.quy_cach import DEFAULTS, invalidate_cache, load_quy_cach, normalize


async def quy_cach_get_handler(request: web.Request):
    cfg = await asyncio.to_thread(load_quy_cach)
    return web.json_response({"ok": True, "quy_cach": cfg, "defaults": DEFAULTS})


async def quy_cach_set_handler(request: web.Request):
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin sửa quy cách được"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("quy_cach") if isinstance(body, dict) else None
    if not isinstance(raw, dict):
        return web.json_response({"ok": False, "error": "Thiếu quy_cach (object)"}, status=400)
    cfg = normalize(raw)   # ép kiểu + chuẩn hoá mã in hoa, số > 0

    def _save():
        from settings_store import set_value
        set_value("parse_quy_cach", cfg)
        invalidate_cache()
        return cfg

    saved = await asyncio.to_thread(_save)

    actor = request.get("web_user")
    if isinstance(actor, dict):
        actor = str(actor.get("display_name") or actor.get("username") or "web")
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.quy_cach", async_log_event(
        "settings.quy_cach_changed", scope="settings", thread_id=0,
        actor_type="web_user", actor_id=str(actor or "web"),
        source="quy_cach.changed", payload=saved))
    return web.json_response({"ok": True, "quy_cach": saved})
