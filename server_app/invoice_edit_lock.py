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


def _lock_info(thread_id: int) -> dict | None:
    """Khoá còn hiệu lực của đơn (None nếu trống/hết hạn). Dọn khoá hết hạn."""
    lk = _edit_locks.get(thread_id)
    if not lk:
        return None
    if (time.monotonic() - lk["at"]) >= _LOCK_TTL:
        _edit_locks.pop(thread_id, None)
        return None
    return lk


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (TypeError, ValueError):
        return None


async def invoice_edit_lock_handler(request: web.Request):
    """Xin/gia hạn khoá sửa hoá đơn. Body {user?}. Trả {holder, mine}.
    mine=False = người khác đang sửa hoá đơn đơn này (client hiện banner, không cho sửa)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    lk = _lock_info(thread_id)
    if lk and lk["user"] != me:   # người khác đang giữ → không cấp
        return web.json_response({"ok": True, "holder": lk["user"], "mine": False})
    was_free = lk is None
    _edit_locks[thread_id] = {"user": me, "at": time.monotonic()}
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
    """Nhả khoá sửa hoá đơn (chỉ khi mình đang giữ). Body {user?}."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    lk = _edit_locks.get(thread_id)
    if lk and lk["user"] == me:
        _edit_locks.pop(thread_id, None)
        from server_app.realtime import emit_invoice_edit_lock
        emit_invoice_edit_lock(thread_id, None)
    return web.json_response({"ok": True})
