"""Realtime push tới web client qua /ws — sự kiện đơn thay đổi / danh sách thay đổi.

Phát tới server_app.state.ws_clients (tập WebSocket đang mở). Điểm phát (emit) là
các choke point refresh sau khi ghi đơn — cả web lẫn Telegram đều đi qua:
  - server_app/order_api_common.refresh_order_bg   (mutation từ webapp)
  - order_commands_v3._refresh_order_message        (lệnh gõ trong Telegram)
  - channel_handlers/register.py                    (đơn mới từ #don_hang)
  - server_app/comment_routes.comments_add_handler  (bình luận web → refresh detail)
Consumer: webapp/src/realtime.ts. Event luôn best-effort — lỗi phát KHÔNG được làm
hỏng đường refresh gọi nó (đã bọc try ở đây).
"""
from __future__ import annotations

import json
import logging

from server_app.state import ws_clients

log = logging.getLogger("server")


async def _send(payload: dict) -> None:
    data = json.dumps(payload, default=str)
    for ws in ws_clients.copy():
        try:
            await ws.send_str(data)
        except Exception:
            ws_clients.discard(ws)


async def broadcast_order_changed(thread_id) -> None:
    """1 đơn đổi → đẩy kèm row danh sách để client vá tại chỗ (dashboard khỏi refetch).
    Kèm thread_id để trang chi tiết tự tải lại đúng đơn đang mở."""
    try:
        from server_app.orders_api import build_row_for_thread
        row = build_row_for_thread(thread_id)
        await _send({"type": "order_changed", "thread_id": str(thread_id), "row": row})
    except Exception as e:
        log.warning("realtime order_changed failed thread=%s: %s", thread_id, e)


async def broadcast_orders_changed() -> None:
    """Thay đổi cấp danh sách (đơn mới / xoá) → client refetch trang hiện tại."""
    try:
        await _send({"type": "orders_changed"})
    except Exception as e:
        log.warning("realtime orders_changed failed: %s", e)
