"""Realtime push tới web client qua /ws — sự kiện đơn thay đổi / danh sách thay đổi.

Phát tới server_app.state.ws_clients (tập WebSocket đang mở). Điểm phát (emit) là
các choke point refresh sau khi ghi đơn — cả web lẫn Telegram đều đi qua:
  - server_app/order_api_common.refresh_order_bg   (mutation từ webapp)
  - order_commands_v3._refresh_order_message        (lệnh gõ trong Telegram)
  - channel_handlers/register.py                    (đơn mới từ #don_hang)
  - server_app/comment_routes.comments_add_handler  (bình luận web → refresh detail)

Dùng emit_* (đồng bộ, không chặn) ở các đường refresh — phát chạy nền qua
spawn_tracked, KHÔNG await trong hot path (1 client treo không được làm chậm
refresh/edit của đơn). Gửi tới từng client song song, mỗi client có timeout; lỗi
gửi thì đóng + loại bỏ (để client thấy close mà tự nối lại, không bị "treo im").
Consumer: webapp/src/realtime.ts.
"""
from __future__ import annotations

import asyncio
import json
import logging

from server_app.state import ws_clients

log = logging.getLogger("server")

_SEND_TIMEOUT = 5.0  # giây — client chậm/ngủ không được chặn cả vòng phát


async def _send_one(ws, data: str) -> None:
    try:
        await asyncio.wait_for(ws.send_str(data), timeout=_SEND_TIMEOUT)
    except Exception:
        ws_clients.discard(ws)
        try:
            await ws.close()  # đóng để client nhận close → tự nối lại (tránh orphan im lặng)
        except Exception:
            pass


async def _send(payload: dict) -> None:
    data = json.dumps(payload, default=str)
    clients = list(ws_clients)
    if not clients:
        return
    await asyncio.gather(*(_send_one(ws, data) for ws in clients), return_exceptions=True)


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


def emit_order_changed(thread_id) -> None:
    """Lên lịch phát 'đơn đổi' chạy nền — gọi từ đường refresh, KHÔNG await."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.order_changed", broadcast_order_changed(thread_id), {"thread_id": thread_id})


def emit_orders_changed() -> None:
    """Lên lịch phát 'danh sách đổi' chạy nền — gọi từ đường tạo đơn, KHÔNG await."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.orders_changed", broadcast_orders_changed())


# ─── Phiếu sản xuất (production) — id-space riêng, sự kiện riêng ──────────────
async def broadcast_production_changed(thread_id) -> None:
    """1 phiếu SX đổi → đẩy kèm row danh sách (client vá tại chỗ + tải lại chi tiết)."""
    try:
        from server_app.production_routes import build_production_row
        row = build_production_row(thread_id)
        await _send({"type": "production_changed", "thread_id": str(thread_id), "row": row})
    except Exception as e:
        log.warning("realtime production_changed failed thread=%s: %s", thread_id, e)


async def broadcast_productions_changed() -> None:
    """Thay đổi cấp danh sách phiếu SX (tạo mới / xoá) → client refetch."""
    try:
        await _send({"type": "productions_changed"})
    except Exception as e:
        log.warning("realtime productions_changed failed: %s", e)


def emit_production_changed(thread_id) -> None:
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.production_changed", broadcast_production_changed(thread_id), {"thread_id": thread_id})


def emit_productions_changed() -> None:
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.productions_changed", broadcast_productions_changed())


# ─── Khách hàng / Kho / Thùng / Bảng giá — sự kiện thô (client tự refetch) ─────
async def _broadcast(payload: dict, what: str) -> None:
    try:
        await _send(payload)
    except Exception as e:  # noqa: BLE001
        log.warning("realtime %s failed: %s", what, e)


def emit_customer_changed(key=None) -> None:
    """Khách đổi (sửa bảng giá riêng / pattern / công nợ). key=firebase_key khách (hoặc None)."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.customer_changed",
                  _broadcast({"type": "customer_changed", "key": None if key is None else str(key)}, "customer_changed"))


def emit_inventory_changed() -> None:
    """Kho đổi (nhập/sửa/vô hiệu thùng, xuất/thu hồi) → trang Kho refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.inventory_changed", _broadcast({"type": "inventory_changed"}, "inventory_changed"))


def emit_box_changed(box_id=None) -> None:
    """1 thùng đổi (sửa ghi chú/số cây/NSX, vô hiệu, xuất/thu hồi, ảnh/bình luận thùng)."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.box_changed",
                  _broadcast({"type": "box_changed", "box_id": None if box_id is None else str(box_id)}, "box_changed"))


def emit_price_lists_changed() -> None:
    """Bảng giá chung đổi (lưu giá) → trang bảng giá + khách refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.price_lists_changed", _broadcast({"type": "price_lists_changed"}, "price_lists_changed"))


def emit_report_lock(thread_id, holder) -> None:
    """Khoá sửa báo cáo phiếu SX đổi chủ (ai đang giữ / None = nhả) → client khác đổi UI."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.report_lock",
                  _broadcast({"type": "report_lock", "thread_id": None if thread_id is None else str(thread_id), "holder": holder}, "report_lock"))


def emit_report_draft(thread_id, draft: dict) -> None:
    """Bản nháp bảng báo cáo (người đang sửa gõ) → người xem thấy trực tiếp. Không lưu DB."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.report_draft",
                  _broadcast({"type": "report_draft", "thread_id": None if thread_id is None else str(thread_id), "draft": draft}, "report_draft"))
