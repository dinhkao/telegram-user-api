"""Khoá SỬA HOÁ ĐƠN của đơn — 1 người mở trang sửa hoá đơn cùng lúc (in-memory, TTL).

ĐƠN GIẢN (giống stock_pick_lock nhưng theo THREAD_ID — mỗi đơn 1 hoá đơn): xin khoá khi
mở trang sửa hoá đơn, gia hạn bằng heartbeat (~20s), nhả khi rời trang (hoặc tự hết hạn 45s
nếu tab chết). Người KHÁC mở trang thấy "X đang sửa hoá đơn" thay vì trình sửa; nút "Sửa hoá
đơn" ở trang chi tiết cũng mờ. KHÔNG chia sẻ nội dung đang gõ — chỉ khoá cho gọn.

Nối: server_app.realtime (emit_invoice_edit_lock), server_app.production_routes (_web_actor).
Đăng ký route ở app_factory; loại khỏi audit ở server_app.audit (_NO_AUDIT).
"""
from __future__ import annotations

import time

from aiohttp import web

from server_app.production_routes import _web_actor

# thread_id → {"user", "at": monotonic}
_edit_locks: dict[int, dict] = {}
_LOCK_TTL = 45.0   # hết hạn nếu client ngừng heartbeat (~mỗi 20s), giống report_lock


def _user_key(user: str | None) -> str:
    return " ".join(str(user or "").split()).casefold()


def _session_key(sid: str | None) -> str:
    return str(sid or "__legacy__")


def _same_user(lock: dict, user: str) -> bool:
    return str(lock.get("user_key") or _user_key(lock.get("user"))) == _user_key(user)


def _lock_info(thread_id: int) -> dict | None:
    """Khoá còn hiệu lực của đơn (None nếu trống/hết hạn). Dọn khoá hết hạn."""
    lk = _edit_locks.get(thread_id)
    if not lk:
        return None
    sessions = lk.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {_session_key(lk.get("sid")): float(lk.get("at") or 0)}
        lk["sessions"] = sessions
    lk["user_key"] = str(lk.get("user_key") or _user_key(lk.get("user")))
    now = time.monotonic()
    for session, heartbeat_at in list(sessions.items()):
        if (now - float(heartbeat_at or 0)) >= _LOCK_TTL:
            sessions.pop(session, None)
    if not sessions:
        _edit_locks.pop(thread_id, None)
        from server_app.realtime import emit_invoice_edit_lock
        emit_invoice_edit_lock(thread_id, None)
        return None
    return lk


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (TypeError, ValueError):
        return None


async def invoice_edit_lock_handler(request: web.Request):
    """Xin/gia hạn khoá sửa hoá đơn. Body {user?, sid}. Trả {holder, mine}.
    mine=False = người khác đang sửa hoá đơn đơn này (client hiện banner, không cho sửa)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    lk = _lock_info(thread_id)
    if lk and not _same_user(lk, me):   # người khác đang giữ → không cấp
        return web.json_response({"ok": True, "holder": lk["user"], "mine": False})
    was_free = lk is None
    if lk is None:
        lk = {"user": me, "user_key": _user_key(me), "sessions": {}}
        _edit_locks[thread_id] = lk
    lk["sessions"][_session_key(sid)] = time.monotonic()
    if was_free:   # chỉ phát khi ĐỔI trạng thái (tránh spam theo heartbeat)
        from server_app.realtime import emit_invoice_edit_lock
        emit_invoice_edit_lock(thread_id, me)
    return web.json_response({"ok": True, "holder": me, "mine": True})


async def invoice_edit_lock_status_handler(request: web.Request):
    """Ai đang sửa hoá đơn đơn này (không xin khoá). Trả {holder}.
    OrderDetail nạp lúc mở để làm mờ nút 'Sửa hoá đơn'."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    lk = _lock_info(thread_id)
    return web.json_response({"ok": True, "holder": lk["user"] if lk else None})


async def invoice_edit_unlock_handler(request: web.Request):
    """Nhả phiên sửa hoá đơn hiện tại. Body {user?, sid}."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    lk = _lock_info(thread_id)
    if lk and _same_user(lk, me) and _session_key(sid) in lk["sessions"]:
        lk["sessions"].pop(_session_key(sid), None)
        if not lk["sessions"]:
            _edit_locks.pop(thread_id, None)
            from server_app.realtime import emit_invoice_edit_lock
            emit_invoice_edit_lock(thread_id, None)
    return web.json_response({"ok": True})
