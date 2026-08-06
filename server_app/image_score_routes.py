"""HTTP CHẤM ĐIỂM 0–10 cho TỪNG ẢNH — POST/DELETE
/api/media/{scope}/{entity_id}/images/{image_id}/score.

Dùng cho ảnh báo cáo vệ sinh khu vực (scope `area_report`) và ảnh mâm kẹo
(`quality_report`); scope nào cũng chấm được miễn nằm trong allowlist của
entity_media_routes.

⚠ ĐIỂM LÀ RIÊNG TỪNG NGƯỜI: mọi user đăng nhập đều chấm được, mỗi người giữ điểm
của mình (khoá (scope, image_id, scored_by) — xem entity_media_store/scores.py).
POST = chấm/sửa điểm CỦA MÌNH; DELETE = bỏ điểm CỦA MÌNH, KHÔNG đụng người khác.
Mọi lần chấm/bỏ đều GHI LOG vào audit (scope 'quality'/'area', action
`*.image_scored` / `*.image_score_cleared`) để tra lại ai chấm gì, lúc nào.
Nối: entity_media_store.scores, server_app.entity_media_routes (allowlist + _emit),
audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from entity_media_store import clear_score, get_image, scores_for, set_score
from server_app.entity_media_routes import _ALLOWED_SCOPES, _deny

# scope ảnh → scope audit + tiền tố action (để trang Lịch sử gom đúng nhóm)
_AUDIT_SCOPE = {"quality_report": "quality", "area_report": "area"}


def _audit_score(request: web.Request, scope: str, entity_id: int, payload: dict, cleared: bool) -> None:
    """Ghi log 1 lần chấm/bỏ điểm. Không chặn response nếu audit lỗi."""
    a_scope = _AUDIT_SCOPE.get(scope)
    if not a_scope:
        return                       # scope lạ (ảnh đơn hàng…) — không có nhóm log riêng
    action = f"{a_scope}.image_score_cleared" if cleared else f"{a_scope}.image_scored"
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope=a_scope, thread_id=entity_id,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=_actor(request), source=action, payload=payload))


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
    # điểm CŨ của chính người này (để ghi log "sửa 7 → 9", nhìn log là thấy đổi gì)
    before = await asyncio.to_thread(scores_for, scope, [image_id], actor)
    old = (before.get(image_id) or {}).get("my_score")
    try:
        row = await asyncio.to_thread(set_score, scope, image_id, body.get("score"), actor)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

    _audit_score(request, scope, entity_id, {
        "image_id": image_id, "entity_id": entity_id, "score": row["score"],
        "old_score": old, "scope": scope,
    }, cleared=False)
    from server_app.entity_media_routes import _emit
    _emit(scope, entity_id)
    # trả kèm tổng hợp mới để client cập nhật ngay (điểm TB + số người chấm)
    after = await asyncio.to_thread(scores_for, scope, [image_id], actor)
    return web.json_response({"ok": True, "score": row, "image": after.get(image_id)})


async def image_score_clear_handler(request: web.Request):
    """DELETE .../images/{image_id}/score — bỏ điểm CỦA MÌNH (điểm người khác giữ nguyên)."""
    scope, entity_id, image_id = _target(request)
    if entity_id is None or image_id is None:
        return web.json_response({"ok": False, "error": "scope/id không hợp lệ"}, status=400)
    d = _deny(request, scope)
    if d:
        return d
    if not await _check_image(scope, entity_id, image_id):
        return web.json_response({"ok": False, "error": "không tìm thấy ảnh"}, status=404)

    actor = _actor(request)
    before = await asyncio.to_thread(scores_for, scope, [image_id], actor)
    old = (before.get(image_id) or {}).get("my_score")
    removed = await asyncio.to_thread(clear_score, scope, image_id, actor)
    if removed:
        _audit_score(request, scope, entity_id, {
            "image_id": image_id, "entity_id": entity_id, "old_score": old, "scope": scope,
        }, cleared=True)
    from server_app.entity_media_routes import _emit
    _emit(scope, entity_id)
    after = await asyncio.to_thread(scores_for, scope, [image_id], actor)
    return web.json_response({"ok": True, "removed": removed, "image": after.get(image_id)})
