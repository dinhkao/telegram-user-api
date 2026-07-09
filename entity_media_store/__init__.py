"""Bình luận + ảnh DÙNG CHUNG cho nhiều loại thực thể (production slip, box…),
khoá theo (scope, entity_id). Tách khỏi order (web_comments/order_images) để không
đụng id. Thuần DB/disk, KHÔNG sync Telegram. Dùng bởi server_app/entity_media_routes.
"""
from .comments import add_comment, list_comments
from .images import add_image, delete_image, get_image, latest_image_ids, list_images

__all__ = ["add_comment", "list_comments", "add_image", "delete_image", "get_image", "latest_image_ids", "list_images"]
