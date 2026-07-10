"""HTTP cài đặt hệ thống — GET/POST /api/settings (đọc: mọi user; ghi: admin).

Key whitelist — thêm toggle mới thì thêm vào _ALLOWED_KEYS. Lưu ở
settings_store (kv_store['app_settings']). Đăng ký ở app_factory.
Nối: settings_store, server_app.order_api_common (is_admin_request), audit_log.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from settings_store import get_all, set_value

# key → mô tả (trả kèm cho UI); default xử lý ở nơi ĐỌC (get_bool(key, default))
_ALLOWED_KEYS = {
    "soan_hang_require_stock": "Ràng buộc quy trình: chốt kho + ảnh → soạn hàng → giao hàng → in HĐ giao",
    "pack_allow_no_material": "Cho phép nhập trực tiếp SP đóng gói không bắt buộc trừ nguyên liệu",
}
_DEFAULTS = {"soan_hang_require_stock": True, "pack_allow_no_material": False}


async def settings_get_handler(request: web.Request):
    data = await asyncio.to_thread(get_all)
    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if k in _ALLOWED_KEYS}}
    return web.json_response({"ok": True, "settings": merged})


async def settings_set_handler(request: web.Request):
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin sửa cài đặt được"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    key = str(body.get("key") or "")
    if key not in _ALLOWED_KEYS:
        return web.json_response({"ok": False, "error": f"Key không hợp lệ: {key}"}, status=400)
    value = bool(body.get("value"))
    data = await asyncio.to_thread(set_value, key, value)

    actor = request.get("web_user")
    if isinstance(actor, dict):
        actor = str(actor.get("display_name") or actor.get("username") or "web")
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.settings", async_log_event(
        "settings.changed", scope="settings", thread_id=0,
        actor_type="web_user", actor_id=str(actor or "web"),
        source="settings.changed", payload={"key": key, "value": value}))
    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if k in _ALLOWED_KEYS}}
    return web.json_response({"ok": True, "settings": merged})
