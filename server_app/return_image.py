"""Tạo ẢNH HOÁ ĐƠN TRẢ HÀNG cho 1 phiếu trả rồi lưu vào ảnh của phiếu (media scope
'return' — hiện ở khối Ảnh trang #/tra-hang/:id, tải/chia sẻ như ảnh thường).

Luồng: return_store (phiếu + tên khách) → order_store.display (tên SP hiện hành) →
renderers.phieu_tra_hang (HTML 280px) → integrations.firebase_html_to_png (Playwright,
cùng pipeline ảnh hoá đơn bán server_app/invoice_image) → order_photo_sync._process_incoming
(full + thumb) → entity_media_store.add_image + file dưới ORDER_MEDIA_DIR/return/<id>/.
Gọi từ server_app/return_image_routes.py (nút bấm) và sau khi tạo HĐ KiotViet
(server_app/return_routes.return_invoice_handler, chạy nền).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

log = logging.getLogger("return_image")


def build_return_html(return_id: int) -> str | None:
    """HTML hoá đơn trả hàng của phiếu (None nếu không có / đã xoá). Blocking — gọi qua thread."""
    from order_store.display import resolve_invoice_display
    from renderers.phieu_tra_hang import generate_return_html
    from return_store import get_return_full
    from utils.db import get_connection
    conn = get_connection()
    try:
        r = get_return_full(conn, int(return_id))
        if not r or r.get("deleted_at"):
            return None
        r = {**r, "items": resolve_invoice_display(r.get("items") or [], conn)}
        return generate_return_html(r, r.get("customer_name") or "")
    finally:
        conn.close()


async def render_return_png(return_id: int) -> bytes | None:
    """PNG hoá đơn trả hàng (None nếu phiếu không tồn tại). Lỗi render → raise."""
    html = await asyncio.to_thread(build_return_html, return_id)
    if html is None:
        return None
    from integrations.firebase_html_to_png.core import _executor, _html_to_png
    from server_app.invoice_image import _read_bytes
    loop = asyncio.get_running_loop()
    png_path = await loop.run_in_executor(_executor, _html_to_png, html, log)
    try:
        return await asyncio.to_thread(_read_bytes, png_path)
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass


def _store(return_id: int, png_bytes: bytes, uploaded_by: str) -> dict:
    """Ghi full + thumb xuống đĩa rồi thêm dòng entity_images (scope 'return')."""
    from entity_media_store import add_image
    from server_app.entity_media_routes import _dir, _safe_path
    from server_app.order_photo_sync import _process_incoming
    full_b, full_ext, mime, thumb_b, thumb_ext, w, h = _process_incoming(png_bytes)
    uid = uuid.uuid4().hex
    fname, tname = f"{uid}{full_ext}", f"{uid}_t{thumb_ext}"
    _dir("return", return_id)
    fp, tp = _safe_path("return", return_id, fname), _safe_path("return", return_id, tname)
    if not fp or not tp:
        raise ValueError("tên file không hợp lệ")
    with open(fp, "wb") as f:
        f.write(full_b)
    with open(tp, "wb") as f:
        f.write(thumb_b)
    return add_image("return", return_id, fname, tname, mime, size=len(full_b),
                     width=w, height=h, uploaded_by=uploaded_by)


async def add_return_image(return_id: int, uploaded_by: str = "Hoá đơn trả hàng") -> dict | None:
    """Render + lưu ảnh hoá đơn trả hàng vào ảnh của phiếu, phát realtime.
    Trả dict ảnh, None nếu phiếu không tồn tại. Lỗi render/lưu → raise (caller quyết)."""
    png = await render_return_png(return_id)
    if png is None:
        return None
    img = await asyncio.to_thread(_store, int(return_id), png, uploaded_by)
    from server_app.realtime import emit_return_changed
    emit_return_changed(int(return_id))
    log.info("return image ok return=%s img=%s", return_id, img.get("id"))
    return img


async def add_return_image_bg(return_id: int, uploaded_by: str = "Hoá đơn trả hàng") -> None:
    """Bản chạy nền (sau khi tạo HĐ KiotViet) — nuốt lỗi, không làm hỏng luồng chính."""
    try:
        await add_return_image(return_id, uploaded_by)
    except Exception as e:  # noqa: BLE001
        log.error("return image nền lỗi return=%s: %s", return_id, e)
