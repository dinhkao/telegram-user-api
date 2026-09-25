"""POST /api/returns/{id}/image — tạo ẢNH HOÁ ĐƠN TRẢ HÀNG (mọi người dùng đăng nhập)
và lưu vào ảnh của phiếu trả. Logic ở server_app/return_image.py; đăng ký ở app_factory.
Lịch sử: audit request (nhãn ở server_app/entity_history._SOURCE_LABELS).
"""
from __future__ import annotations

import logging

from aiohttp import web

log = logging.getLogger("return_image_routes")


async def return_image_handler(request: web.Request):
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    u = request.get("web_user")
    who = str((u.get("display_name") or u.get("username")) if isinstance(u, dict) else (u or "web"))
    from server_app.return_image import add_return_image
    try:
        img = await add_return_image(rid, uploaded_by=who)
    except Exception as e:  # noqa: BLE001
        log.error("tạo ảnh phiếu trả #%s lỗi: %s", rid, e)
        return web.json_response({"ok": False, "error": "Tạo ảnh hoá đơn trả hàng lỗi — thử lại"}, status=502)
    if img is None:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    return web.json_response({"ok": True, "image": img})
