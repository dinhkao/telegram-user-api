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


def emit_notif_added(notif: dict) -> None:
    """Thông báo mới (notification center) → client cập nhật chuông + danh sách."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.notif_added", _broadcast({"type": "notif_added", "notif": notif}, "notif_added"))


def emit_banner_changed() -> None:
    """Bảng tin banner đổi (ghim/gỡ bình luận) → client tải lại banner."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.banner_changed", _broadcast({"type": "banner_changed"}, "banner_changed"))


def emit_quy_changed() -> None:
    """Sổ quỹ đổi (tạo/xoá phiếu thu/chi, thanh toán tiền mặt của đơn) → trang Quỹ refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.quy_changed", _broadcast({"type": "quy_changed"}, "quy_changed"))


def emit_tasks_changed() -> None:
    """Việc (task list) đổi → trang Việc refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.tasks_changed", _broadcast({"type": "tasks_changed"}, "tasks_changed"))


def emit_return_changed(return_id) -> None:
    """Phiếu trả hàng đổi (sửa/tạo HĐ/ảnh/bình luận) → chi tiết + dashboard trả hàng."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.return_changed",
                  _broadcast({"type": "return_changed", "id": str(return_id)}, "return_changed"))


def emit_purchase_changed(purchase_id) -> None:
    """Phiếu nhập hàng đổi (tạo/sửa/xoá/ảnh/bình luận) → chi tiết + dashboard nhập hàng."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.purchase_changed",
                  _broadcast({"type": "purchase_changed", "id": str(purchase_id)}, "purchase_changed"))


def emit_disposal_changed(disposal_id) -> None:
    """Phiếu xuất hủy đổi (tạo/xoá/ảnh/bình luận) → chi tiết + dashboard xuất hủy."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.disposal_changed",
                  _broadcast({"type": "disposal_changed", "id": str(disposal_id)}, "disposal_changed"))


def emit_cashbox_changed() -> None:
    """Hệ két tiền đổi (chuyển tay tạo/xoá) → trang Két refetch. Biến động từ
    đơn hàng thì client nghe order_changed/orders_changed sẵn có."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.cashbox_changed", _broadcast({"type": "cashbox_changed"}, "cashbox_changed"))


def emit_supplier_changed(supplier_id=None) -> None:
    """Nhà cung cấp đổi (tạo/sửa/xoá, hoặc thống kê đổi vì phiếu nhập) → list + chi tiết NCC."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.supplier_changed",
                  _broadcast({"type": "supplier_changed",
                              "id": str(supplier_id) if supplier_id is not None else None},
                             "supplier_changed"))


def emit_workers_changed() -> None:
    """Danh sách thợ đổi (thêm/sửa/xoá/sắp thứ tự) → trang Thợ refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.workers_changed", _broadcast({"type": "workers_changed"}, "workers_changed"))


def emit_report_slips_changed() -> None:
    """Phiếu báo cáo SX đổi (tạo/xoá) → trang Báo cáo refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.report_slips_changed", _broadcast({"type": "report_slips_changed"}, "report_slips_changed"))


def emit_price_lists_changed() -> None:
    """Bảng giá chung đổi (lưu giá) → trang bảng giá + khách refetch."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.price_lists_changed", _broadcast({"type": "price_lists_changed"}, "price_lists_changed"))


def emit_stock_pick_lock(thread_id, code, holder) -> None:
    """Khoá chọn thùng xuất kho cho (đơn, mã SP) đổi chủ (holder / None = nhả) → client khác
    làm mờ hoặc bỏ mờ nút 'Chọn thùng' của mã đó."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.stock_pick_lock",
                  _broadcast({"type": "stock_pick_lock", "thread_id": None if thread_id is None else str(thread_id), "code": code, "holder": holder}, "stock_pick_lock"))


def emit_invoice_edit_lock(thread_id, holder) -> None:
    """Khoá sửa hoá đơn của đơn đổi chủ (holder / None = nhả) → client khác làm mờ hoặc bỏ mờ
    nút 'Sửa hoá đơn' và trang sửa hiện/ẩn banner 'X đang sửa'."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.invoice_edit_lock",
                  _broadcast({"type": "invoice_edit_lock", "thread_id": None if thread_id is None else str(thread_id), "holder": holder}, "invoice_edit_lock"))


def emit_invoice_creating(thread_id, holder) -> None:
    """Đang TẠO hoá đơn KiotViet cho đơn (holder = người bấm; None = xong/nhả). Client
    khác khoá nút 'Tạo HĐ KiotViet' + KHÔNG hiện popup xác nhận để tránh tạo HĐ trùng
    (backend đã chống trùng bằng _invoice_create_lock; đây là lớp phối hợp UI)."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.invoice_creating",
                  _broadcast({"type": "invoice_creating", "thread_id": None if thread_id is None else str(thread_id), "holder": holder}, "invoice_creating"))


def emit_report_lock(thread_id, holder) -> None:
    """Khoá sửa báo cáo phiếu SX đổi chủ (ai đang giữ / None = nhả) → client khác đổi UI."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.report_lock",
                  _broadcast({"type": "report_lock", "thread_id": None if thread_id is None else str(thread_id), "holder": holder}, "report_lock"))


def emit_stocktake_lock(stocktake_id, holder) -> None:
    """Người đang kiểm một phiếu/kho đổi → máy khác cập nhật quyền sửa ngay."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.stocktake_lock", _broadcast({
        "type": "stocktake_lock",
        "stocktake_id": None if stocktake_id is None else str(stocktake_id),
        "holder": holder,
    }, "stocktake_lock"))


def emit_report_draft(thread_id, draft: dict) -> None:
    """Bản nháp bảng báo cáo (người đang sửa gõ) → người xem thấy trực tiếp. Không lưu DB."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.report_draft",
                  _broadcast({"type": "report_draft", "thread_id": None if thread_id is None else str(thread_id), "draft": draft}, "report_draft"))


def emit_app_reload() -> None:
    """ÉP mọi client web đang mở tải lại trang (lấy bundle mới nhất). Client nhận
    'app_reload' → window.location.reload(). Chỉ tới được máy ĐÃ có bản có listener này."""
    from server_app.tasks import spawn_tracked
    spawn_tracked("realtime.app_reload", _broadcast({"type": "app_reload"}, "app_reload"))
