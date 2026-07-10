"""Khoá CHỌN THÙNG xuất kho cho đơn — 1 người/(đơn, mã SP) mở popup cùng lúc (in-memory, TTL).

ĐƠN GIẢN: xin khoá khi mở popup chọn thùng, gia hạn bằng heartbeat (~20s), nhả khi đóng
(hoặc tự hết hạn 45s nếu tab chết). Người KHÁC thấy nút "Chọn thùng" của mã đó bị mờ ("đang
được X chọn"). KHÔNG chia sẻ lựa chọn/nháp — chỉ khoá nút cho gọn. Khoá theo (thread_id, mã
SP) nên 2 người chọn 2 mã KHÁC của cùng 1 đơn không cản nhau.

Nối: server_app.realtime (emit_stock_pick_lock), server_app.production_routes (_web_actor).
Đăng ký route ở app_factory; loại khỏi audit ở server_app.audit (_NO_AUDIT).
"""
from __future__ import annotations

import time

from aiohttp import web

from server_app.production_routes import _web_actor

# "thread_id:CODE" → {"user", "at": monotonic, "code", "thread_id"}
_pick_locks: dict[str, dict] = {}
_LOCK_TTL = 45.0   # hết hạn nếu client ngừng heartbeat (~mỗi 20s), giống report_lock


def _key(thread_id: int, code: str) -> str:
    return f"{thread_id}:{(code or '').strip().upper()}"


def _lock_info(key: str) -> dict | None:
    """Khoá còn hiệu lực (None nếu trống/hết hạn). Dọn khoá hết hạn."""
    lk = _pick_locks.get(key)
    if not lk:
        return None
    if (time.monotonic() - lk["at"]) >= _LOCK_TTL:
        _pick_locks.pop(key, None)
        return None
    return lk


def locks_for_thread(thread_id: int) -> dict:
    """{CODE: holder} các mã đang có người chọn thùng cho đơn này (bỏ hết hạn)."""
    out: dict = {}
    prefix = f"{thread_id}:"
    for k in list(_pick_locks.keys()):
        if k.startswith(prefix):
            lk = _lock_info(k)
            if lk:
                out[lk["code"]] = lk["user"]
    return out


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (TypeError, ValueError):
        return None


async def stock_pick_lock_handler(request: web.Request):
    """Xin/gia hạn khoá chọn thùng. Body {user?, code}. Trả {holder, mine, code}.
    mine=False = người khác đang chọn mã này (client tự đóng popup)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str(body.get("code") or "").strip().upper()
    me = _web_actor(request, body)
    key = _key(thread_id, code)
    lk = _lock_info(key)
    if lk and lk["user"] != me:   # người khác đang giữ → không cấp
        return web.json_response({"ok": True, "holder": lk["user"], "mine": False, "code": code})
    was_free = lk is None
    _pick_locks[key] = {"user": me, "at": time.monotonic(), "code": code, "thread_id": thread_id}
    if was_free:   # chỉ phát khi ĐỔI trạng thái (tránh spam theo heartbeat)
        from server_app.realtime import emit_stock_pick_lock
        emit_stock_pick_lock(thread_id, code, me)
    return web.json_response({"ok": True, "holder": me, "mine": True, "code": code})


async def stock_pick_lock_status_handler(request: web.Request):
    """Xem các mã đang có người chọn thùng cho đơn (không xin khoá). Trả {locks:{code:holder}}.
    OrderStock nạp lúc mở để làm mờ nút 'Chọn thùng' của mã đang bị người khác chọn."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    return web.json_response({"ok": True, "locks": locks_for_thread(thread_id)})


async def stock_pick_unlock_handler(request: web.Request):
    """Nhả khoá chọn thùng (chỉ khi mình đang giữ). Body {user?, code}."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str(body.get("code") or "").strip().upper()
    me = _web_actor(request, body)
    key = _key(thread_id, code)
    lk = _pick_locks.get(key)
    if lk and lk["user"] == me:
        _pick_locks.pop(key, None)
        from server_app.realtime import emit_stock_pick_lock
        emit_stock_pick_lock(thread_id, code, None)
    return web.json_response({"ok": True})
