"""HTTP handlers quản lý user web app — /api/users*. CHỈ admin.

Layer mỏng trên user_store (add/list/set_role/set_disabled/set_pin). Mọi handler
gác bằng is_admin_request (token → role admin). Đăng ký ở app_factory.
Client: webapp/src/pages/Users.tsx.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from server_app.order_api_common import is_admin_request
from user_store import ROLES, add_user, list_users, set_disabled, set_pin, set_role

log = logging.getLogger("server")


async def _require_admin(request):
    return await is_admin_request(request)


async def users_list_handler(request: web.Request):
    if not await _require_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin"}, status=403)
    users = await asyncio.to_thread(list_users)
    # không trả pin_hash
    out = [{"username": u["username"], "display_name": u["display_name"],
            "role": u["role"], "disabled": bool(u["disabled"])} for u in users]
    return web.json_response({"ok": True, "users": out, "roles": list(ROLES)})


async def users_create_handler(request: web.Request):
    if not await _require_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get("username") or "").strip().lower()
    pin = (body.get("pin") or "").strip()
    name = (body.get("display_name") or "").strip()
    role = (body.get("role") or "staff").strip()
    if not username or not pin:
        return web.json_response({"ok": False, "error": "Thiếu username hoặc PIN"}, status=400)
    if role not in ROLES:
        return web.json_response({"ok": False, "error": f"Vai trò không hợp lệ: {role}"}, status=400)
    try:
        u = await asyncio.to_thread(add_user, username, pin, display_name=name, role=role)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "user": {"username": u["username"], "display_name": u["display_name"], "role": u["role"]}})


async def users_role_handler(request: web.Request):
    if not await _require_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin"}, status=403)
    username = (request.match_info.get("username") or "").strip().lower()
    try:
        body = await request.json()
    except Exception:
        body = {}
    role = (body.get("role") or "").strip()
    if role not in ROLES:
        return web.json_response({"ok": False, "error": f"Vai trò không hợp lệ: {role}"}, status=400)
    # Không cho admin tự hạ quyền chính mình (tránh khoá cửa)
    if username == (request.get("web_user") or "").strip().lower() and role != "admin":
        return web.json_response({"ok": False, "error": "Không thể tự hạ vai trò admin của chính mình"}, status=400)
    ok = await asyncio.to_thread(set_role, username, role)
    if not ok:
        return web.json_response({"ok": False, "error": "Không thấy user"}, status=404)
    return web.json_response({"ok": True})


async def users_disabled_handler(request: web.Request):
    if not await _require_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin"}, status=403)
    username = (request.match_info.get("username") or "").strip().lower()
    try:
        body = await request.json()
    except Exception:
        body = {}
    disabled = bool(body.get("disabled"))
    if username == (request.get("web_user") or "").strip().lower() and disabled:
        return web.json_response({"ok": False, "error": "Không thể tự khoá chính mình"}, status=400)
    ok = await asyncio.to_thread(set_disabled, username, disabled)
    if not ok:
        return web.json_response({"ok": False, "error": "Không thấy user"}, status=404)
    return web.json_response({"ok": True})


async def users_pin_handler(request: web.Request):
    if not await _require_admin(request):
        return web.json_response({"ok": False, "error": "Chỉ admin"}, status=403)
    username = (request.match_info.get("username") or "").strip().lower()
    try:
        body = await request.json()
    except Exception:
        body = {}
    pin = (body.get("pin") or "").strip()
    if not pin:
        return web.json_response({"ok": False, "error": "PIN trống"}, status=400)
    try:
        ok = await asyncio.to_thread(set_pin, username, pin)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    if not ok:
        return web.json_response({"ok": False, "error": "Không thấy user"}, status=404)
    return web.json_response({"ok": True})
