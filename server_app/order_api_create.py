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

import hashlib
import time

from aiohttp import web

from channel_handlers.config import CHANNEL_DON_HANG_MOI
from channel_handlers.create import process_new_order
from server_app import state
from server_app.telegram_helpers import tg_send_message

# Chống DOUBLE-TAP: mỗi request tạo đơn GỬI 1 TIN MỚI vào kênh (message_id mới)
# nên idempotency theo message_id của process_new_order không đỡ được — 2 tap =
# 2 tin = 2 topic = 2 đơn. Guard theo (người tạo, sha1 text chuẩn hoá): ghi key
# TRƯỚC khi gửi Telegram (chặn cả request thứ 2 đến khi request đầu còn đang bay),
# chỉ gỡ khi tạo THẤT BẠI → tạo thành công chặn lặp trong _DUP_TTL giây.
_DUP_TTL = 20.0
_recent_creates: dict[tuple[str, str], float] = {}


def _dup_key(actor: str, text: str) -> tuple[str, str]:
    norm = " ".join((text or "").split()).lower()
    return (str(actor or ""), hashlib.sha1(norm.encode("utf-8")).hexdigest())


def _mark_create(key: tuple[str, str], now: float | None = None) -> bool:
    """Ghi nhận 1 lượt tạo; False = key này vừa tạo/đang tạo < _DUP_TTL → chặn.
    Tiện thể dọn entry đã quá TTL (map nhỏ, 1 vòng quét là đủ)."""
    t = time.monotonic() if now is None else now
    for k, ts in list(_recent_creates.items()):
        if t - ts >= _DUP_TTL:
            _recent_creates.pop(k, None)
    if key in _recent_creates:
        return False
    _recent_creates[key] = t
    return True


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

    # web_actor = người đăng nhập webapp (từ token web_auth) → ghi NGƯỜI TẠO đơn
    # (web gửi bằng tk bot). Tính TRƯỚC để làm key chống double-tap.
    web_actor = request.get("web_user") or (body.get("user") or "").strip() or None
    dup_key = _dup_key(web_actor or request.remote or "", text)
    if not _mark_create(dup_key):
        return web.json_response(
            {"ok": False, "error": "Đơn giống hệt vừa được tạo — kiểm tra danh sách trước khi tạo lại"},
            status=409)

    # 1) Đăng vào kênh #don_hang (bản ghi kênh như gõ tay)
    try:
        sent = await tg_send_message(CHANNEL_DON_HANG_MOI, text)
    except Exception as exc:
        _recent_creates.pop(dup_key, None)   # thất bại → mở lại cho tạo lại ngay
        return web.json_response({"ok": False, "error": f"không gửi được vào kênh #don_hang: {exc}"}, status=502)
    if not getattr(sent, "id", None):
        _recent_creates.pop(dup_key, None)
        return web.json_response({"ok": False, "error": "gửi kênh không trả về message_id"}, status=502)

    # 2) Tạo topic + đơn ngay từ tin vừa đăng (không chờ listener).
    try:
        thread_id = await process_new_order(client, sent, web_actor=web_actor, customer_key=customer_key)
    except Exception as exc:
        _recent_creates.pop(dup_key, None)
        return web.json_response({"ok": False, "error": f"tạo đơn thất bại: {exc}"}, status=500)
    if thread_id is None:
        _recent_creates.pop(dup_key, None)
        return web.json_response({"ok": False, "error": "không tạo được đơn từ tin đã đăng"}, status=500)
    return web.json_response({"ok": True, "thread_id": thread_id, "message_id": sent.id})
