"""POST /api/order/create — tạo đơn mới từ web app.

Đăng nội dung đơn vào kênh #don_hang (CHANNEL_DON_HANG_MOI) như 1 tin nhắn
Telegram bình thường; listener channel_handlers/register.py bắt tin đó → tạo
forum topic + row đơn (thread_id DƯƠNG, flow_version 2) y hệt đơn gõ tay trên
Telegram. Backend chờ (poll) row xuất hiện theo message_id rồi trả thread_id
để web điều hướng thẳng sang trang chi tiết. Không còn tạo đơn DB-only.

Connects to: server_app.telegram_helpers (gửi kênh), channel_handlers.config
(id kênh), order_db (tra đơn theo message_id). Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from channel_handlers.config import CHANNEL_DON_HANG_MOI
from order_db import _get_connection
from server_app.telegram_helpers import tg_send_message

# Poll đợi listener tạo đơn: 0.25s × 48 ≈ 12s (CreateForumTopic + insert thường <1s)
_WAIT_STEP = 0.25
_WAIT_TRIES = 48


def _find_thread_by_msg(message_id: int) -> int | None:
    """thread_id của đơn mà listener vừa tạo cho tin #don_hang này (theo message_id)."""
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT thread_id FROM orders WHERE message_id = ? AND channel_id = ? "
            "AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 1",
            (message_id, CHANNEL_DON_HANG_MOI),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


async def _wait_for_thread(message_id: int) -> int | None:
    for _ in range(_WAIT_TRIES):
        tid = await asyncio.to_thread(_find_thread_by_msg, message_id)
        if tid is not None:
            return tid
        await asyncio.sleep(_WAIT_STEP)
    return None


async def order_create_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    text = str(body.get("text") or "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "thiếu text đơn hàng"}, status=400)

    # Đăng vào kênh #don_hang như tin Telegram bình thường → listener lo phần còn lại
    try:
        sent = await tg_send_message(CHANNEL_DON_HANG_MOI, text)
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"không gửi được vào kênh #don_hang: {exc}"}, status=502)
    message_id = getattr(sent, "id", None)
    if not message_id:
        return web.json_response({"ok": False, "error": "gửi kênh không trả về message_id"}, status=502)

    thread_id = await _wait_for_thread(message_id)
    if thread_id is None:
        # Đã đăng nhưng listener chưa kịp tạo đơn — web hiện "đang tạo", dashboard tự cập nhật
        return web.json_response({"ok": True, "pending": True, "message_id": message_id})
    return web.json_response({"ok": True, "thread_id": thread_id, "message_id": message_id})
