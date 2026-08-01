"""HTTP CHẤM ĐIỂM 0–10 cho TỪNG ẢNH — POST/DELETE
/api/media/{scope}/{entity_id}/images/{image_id}/score.

Dùng cho ảnh báo cáo vệ sinh khu vực (scope `area_report`) và ảnh mâm kẹo
(`quality_report`); scope nào cũng chấm được miễn nằm trong allowlist của
entity_media_routes. MỌI user đăng nhập chấm được — lưu kèm AI chấm (`scored_by`)
để nhìn là biết trách nhiệm. Chấm lại = ghi đè; DELETE = bỏ điểm.
Nối: entity_media_store.scores, server_app.entity_media_routes (allowlist + _emit).
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from entity_media_store import clear_score, get_image, set_score
from server_app.entity_media_routes import _ALLOWED_SCOPES, _deny


def _target(request: web.Request):
    """(scope, entity_id, image_id) hợp lệ, hoặc (None, None, None)."""
    scope = request.match_info.get("scope", "")
    if scope not in _ALLOWED_SCOPES:
        return None, None, None
    try:
        return scope, int(request.match_info.get("entity_id", "")), int(request.match_info.get("image_id", ""))
    except (TypeError, ValueError):
        return scope, None, None


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "?")


async def _check_image(scope: str, entity_id: int, image_id: int):
    """Ảnh phải TỒN TẠI và đúng (scope, entity_id) — không cho chấm điểm chéo thực thể."""
    img = await asyncio.to_thread(get_image, image_id)
    if not img or img.get("scope") != scope or int(img.get("entity_id") or 0) != int(entity_id):
        return None
    return img


async def image_score_set_handler(request: web.Request):
    """POST .../images/{image_id}/score {score: 0..10} — chấm/ghi đè điểm 1 ảnh."""
    scope, entity_id, image_id = _target(request)
    if entity_id is None or image_id is None:
        return web.json_response({"ok": False, "error": "scope/id không hợp lệ"}, status=400)
    d = _deny(request, scope)
    if d:
        return d
    if not await _check_image(scope, entity_id, image_id):
        return web.json_response({"ok": False, "error": "không tìm thấy ảnh"}, status=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)

    actor = _actor(request)
    try:
        row = await asyncio.to_thread(set_score, scope, image_id, body.get("score"), actor)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

    from server_app.entity_media_routes import _emit
    _emit(scope, entity_id)
    return web.json_response({"ok": True, "score": row})


async def image_score_clear_handler(request: web.Request):
    """DELETE .../images/{image_id}/score — bỏ điểm (về 'chưa chấm')."""
    scope, entity_id, image_id = _target(request)
    if entity_id is None or image_id is None:
        return web.json_response({"ok": False, "error": "scope/id không hợp lệ"}, status=400)
    d = _deny(request, scope)
    if d:
        return d
    if not await _check_image(scope, entity_id, image_id):
        return web.json_response({"ok": False, "error": "không tìm thấy ảnh"}, status=404)

    await asyncio.to_thread(clear_score, scope, image_id)
    from server_app.entity_media_routes import _emit
    _emit(scope, entity_id)
    return web.json_response({"ok": True})
