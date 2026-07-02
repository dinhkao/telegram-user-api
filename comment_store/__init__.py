"""comment_store — bảng `web_comments` trong app.db: bình luận trên trang chi tiết
đơn của web app (tách khỏi `order_chat_messages` = log chat Telegram, chỉ đọc).

Ai dùng: server_app/comment_routes. DB-only theo thiết kế — không gửi Telegram.
"""
from comment_store.comments import add_comment, list_comments

__all__ = ["add_comment", "list_comments"]
