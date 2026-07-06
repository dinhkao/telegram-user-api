"""Render phiếu thu (HTML → PNG) rồi thêm vào thư viện ảnh của đơn (loại nộp tiền).

Dùng khi tạo thanh toán (server_app/order_api_payments) để ảnh phiếu thu hiện
TRONG WEBAPP — song song luồng gửi ảnh phiếu thu qua Telegram
(receipt_print.send_payment_receipt). Render CỤC BỘ bằng Playwright
(integrations/firebase_html_to_png.core, giống hoá đơn), lưu qua
image_routes.persist_order_image (kind='nop_tien') + phát realtime. KHÔNG đẩy lên
Telegram (việc đó receipt_print lo). Kết nối: printouts.receipt_print,
integrations.firebase_html_to_png, server_app.image_routes/order_photo_sync/realtime.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("server")


async def add_receipt_image_to_gallery(thread_id: int, customer_name: str, payment_amount: int,
                                       old_debt: int | None = None, new_debt: int | None = None,
                                       uploaded_by: str = "Phiếu thu") -> dict | None:
    """HTML phiếu thu → PNG → thêm vào gallery (kind nộp tiền) + realtime.
    Trả về dict ảnh hoặc None nếu lỗi. Mọi lỗi được nuốt + log (chạy nền, không
    được làm hỏng luồng thanh toán)."""
    # 1) HTML phiếu thu
    try:
        from receipt_print import generate_receipt_html
        html, _ = generate_receipt_html(customer_name, int(thread_id), old_debt, int(payment_amount), new_debt)
    except Exception as e:  # noqa: BLE001
        log.error("receipt image: render HTML lỗi thread=%s: %s", thread_id, e)
        return None

    # 2) HTML → PNG cục bộ (Playwright), đọc bytes rồi xoá file tạm
    png_path = None
    try:
        from integrations.firebase_html_to_png.core import _executor, _html_to_png
        loop = asyncio.get_running_loop()
        png_path = await loop.run_in_executor(_executor, _html_to_png, html, log)
        png_bytes = await asyncio.to_thread(_read_bytes, png_path)
    except Exception as e:  # noqa: BLE001
        log.error("receipt image: HTML→PNG lỗi thread=%s: %s", thread_id, e)
        return None
    finally:
        if png_path:
            try:
                os.unlink(png_path)
            except OSError:
                pass

    # 3) full+thumb → gallery (kind nộp tiền) + realtime + audit
    try:
        from server_app.order_photo_sync import _process_incoming
        full_b, full_ext, mime, thumb_b, thumb_ext, w, h = await asyncio.to_thread(_process_incoming, png_bytes)
        from server_app.image_routes import persist_order_image
        img = await persist_order_image(
            int(thread_id), full_b, mime, full_ext, thumb_b, thumb_ext,
            width=w, height=h, uploaded_by=uploaded_by, kind="nop_tien",
        )
        from server_app.realtime import emit_order_changed
        emit_order_changed(int(thread_id))
        from audit_log import async_log_event
        await async_log_event("order.image_added", actor_type="system", actor_id=uploaded_by,
                              thread_id=int(thread_id), payload={"image_id": img["id"], "source": "payment_receipt"})
        log.info("receipt image → gallery ok thread=%s img=%s", thread_id, img["id"])
        return img
    except Exception as e:  # noqa: BLE001
        log.error("receipt image: lưu gallery lỗi thread=%s: %s", thread_id, e)
        return None


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
