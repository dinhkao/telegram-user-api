"""POST /api/order/create — tạo đơn mới từ web app.

Đăng nội dung đơn vào kênh #don_hang (CHANNEL_DON_HANG_MOI) như 1 tin Telegram,
rồi gọi THẲNG channel_handlers.create.process_new_order(client, sent) để tạo
forum topic + row đơn (thread_id DƯƠNG, flow_version 2) y hệt đơn gõ tay.

Phải gọi thẳng chứ không trông chờ listener: Telethon KHÔNG phát NewMessage cho
tin do chính client gửi, nên đường web tự chạy lõi tạo đơn. process_new_order
idempotent theo message_id nên nếu listener có chạy cũng không tạo trùng.

Connects to: server_app.telegram_helpers, server_app.state (_client),
channel_handlers.create + .config. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

from aiohttp import web

from channel_handlers.config import CHANNEL_DON_HANG_MOI
from channel_handlers.create import process_new_order
from server_app import state
from server_app.telegram_helpers import tg_send_message


async def order_create_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    text = str(body.get("text") or "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "thiếu text đơn hàng"}, status=400)
    # Khách người dùng CHỌN TAY ở webapp (tùy chọn) → đè lên tự nhận diện từ text.
    customer_key = str(body.get("customer_key") or "").strip() or None

    client = state._client
    if client is None:
        return web.json_response({"ok": False, "error": "Telegram client chưa sẵn sàng"}, status=503)

    # 1) Đăng vào kênh #don_hang (bản ghi kênh như gõ tay)
    try:
        sent = await tg_send_message(CHANNEL_DON_HANG_MOI, text)
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"không gửi được vào kênh #don_hang: {exc}"}, status=502)
    if not getattr(sent, "id", None):
        return web.json_response({"ok": False, "error": "gửi kênh không trả về message_id"}, status=502)

    # 2) Tạo topic + đơn ngay từ tin vừa đăng (không chờ listener). web_actor = người
    #    đăng nhập webapp (từ token web_auth) → ghi NGƯỜI TẠO đơn (web gửi bằng tk bot).
    web_actor = request.get("web_user") or (body.get("user") or "").strip() or None
    try:
        thread_id = await process_new_order(client, sent, web_actor=web_actor, customer_key=customer_key)
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"tạo đơn thất bại: {exc}"}, status=500)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "không tạo được đơn từ tin đã đăng"}, status=500)
    return web.json_response({"ok": True, "thread_id": thread_id, "message_id": sent.id})
