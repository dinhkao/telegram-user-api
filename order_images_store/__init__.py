"""Ảnh đính kèm đơn — metadata bảng `order_images` (app.db).

Chỉ giữ metadata (tên file, kích thước, người tải…); file ảnh thật nằm trên đĩa
dưới utils.paths.ORDER_MEDIA_DIR/<thread_id>/. Dùng bởi: server_app/image_routes.
"""
from order_images_store.images import (
    add_image,
    delete_image,
    get_image,
    has_tg_message,
    list_images,
    set_tg_message_id,
)

__all__ = [
    "add_image", "delete_image", "get_image", "has_tg_message",
    "list_images", "set_tg_message_id",
]
