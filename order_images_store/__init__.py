"""Ảnh đính kèm đơn — metadata bảng `order_images` (app.db).

Chỉ giữ metadata (tên file, kích thước, người tải…); file ảnh thật nằm trên đĩa
dưới utils.paths.ORDER_MEDIA_DIR/<thread_id>/. Dùng bởi: server_app/image_routes.
"""
from order_images_store.images import (
    KINDS,
    DEFAULT_KIND,
    add_image,
    delete_image,
    get_image,
    has_tg_message,
    list_images,
    norm_kind,
    set_tg_message_id,
    update_kind,
)
from order_images_store.comments import (
    add_image_comment,
    delete_image_comment,
    list_image_comments,
)

__all__ = [
    "KINDS", "DEFAULT_KIND", "norm_kind", "update_kind",
    "add_image", "delete_image", "get_image", "has_tg_message",
    "list_images", "set_tg_message_id",
    "add_image_comment", "delete_image_comment", "list_image_comments",
]
