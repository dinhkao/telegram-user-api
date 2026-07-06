"""Render hoá đơn KiotViet (HTML → PNG) rồi thêm vào thư viện ảnh của đơn.

Dùng khi webapp tạo HĐ KiotViet thành công (server_app/order_api_invoice) để hình
hoá đơn hiện trong gallery đơn — song song luồng Telegram
(order_commands_v3._send_invoice_html_file). Render CỤC BỘ bằng Playwright
(integrations/firebase_html_to_png.core, giống lệnh Telegram), lưu qua
image_routes.persist_order_image + phát realtime. KHÔNG đẩy ảnh lên Telegram
(chỉ hiện trong webapp). Kết nối: order_db, renderers.inhoadon,
integrations.firebase_html_to_png, server_app.image_routes/order_photo_sync/realtime.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("server")


async def add_invoice_image_to_gallery(thread_id: int, uploaded_by: str = "KiotViet HĐ") -> dict | None:
    """Đọc HĐ KiotViet của đơn → render HTML → PNG → thêm vào gallery + realtime.
    Trả về dict ảnh (như persist_order_image) hoặc None nếu đơn chưa có HĐ / lỗi.
    Mọi lỗi được nuốt + log (chạy nền, không được làm hỏng luồng tạo HĐ)."""
    from order_db import _get_connection, get_customer_by_key, get_order_by_thread_id

    conn = _get_connection()
    order = get_order_by_thread_id(conn, int(thread_id))
    if not order:
        return None
    invoice_id = order.get("kiotvietInvoiceID")
    if not invoice_id:
        return None
    debt = order.get("invoice_debt_snapshot", 0) or 0
    kh_name = "Khách hàng"
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if kh_id_fb:
        c = get_customer_by_key(conn, str(kh_id_fb))
        if c:
            kh_name = c.get("name", "Khách hàng")
    hints = {"customerNameOverride": kh_name, "expectedVAT": 0, "expectedPVC": 0, "disableQR": True}

    # 1) HTML hoá đơn (giống api_invoice_html_handler)
    try:
        from renderers.inhoadon import generate_invoice_html
        html = await asyncio.to_thread(generate_invoice_html, int(invoice_id), debt, hints)
    except Exception as e:  # noqa: BLE001
        log.error("invoice image: render HTML lỗi thread=%s inv=%s: %s", thread_id, invoice_id, e)
        return None

    # 2) HTML → PNG cục bộ (Playwright), đọc bytes rồi xoá file tạm
    png_path = None
    try:
        from integrations.firebase_html_to_png.core import _executor, _html_to_png
        loop = asyncio.get_running_loop()
        png_path = await loop.run_in_executor(_executor, _html_to_png, html, log)
        png_bytes = await asyncio.to_thread(_read_bytes, png_path)
    except Exception as e:  # noqa: BLE001
        log.error("invoice image: HTML→PNG lỗi thread=%s: %s", thread_id, e)
        return None
    finally:
        if png_path:
            try:
                os.unlink(png_path)
            except OSError:
                pass

    # 3) full+thumb → gallery + realtime + audit
    try:
        from server_app.order_photo_sync import _process_incoming
        full_b, full_ext, mime, thumb_b, thumb_ext, w, h = await asyncio.to_thread(_process_incoming, png_bytes)
        from server_app.image_routes import persist_order_image
        img = await persist_order_image(
            int(thread_id), full_b, mime, full_ext, thumb_b, thumb_ext,
            width=w, height=h, uploaded_by=uploaded_by, kind="hoa_don",
        )
        from server_app.realtime import emit_order_changed
        emit_order_changed(int(thread_id))
        from audit_log import async_log_event
        await async_log_event("order.image_added", actor_type="system", actor_id=uploaded_by,
                              thread_id=int(thread_id), payload={"image_id": img["id"], "source": "kiotviet_invoice"})
        log.info("invoice image → gallery ok thread=%s inv=%s img=%s", thread_id, invoice_id, img["id"])
        return img
    except Exception as e:  # noqa: BLE001
        log.error("invoice image: lưu gallery lỗi thread=%s: %s", thread_id, e)
        return None


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
