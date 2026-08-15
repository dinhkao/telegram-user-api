"""notif_store — bảng `notifications` (app.db): nhật ký thông báo cho notification
center webapp. Ghi cùng lúc với push FCM (server_app/notify.py). API:
server_app/notify.py (ghi) + GET /api/notifications (đọc).

Kèm bảng `fcm_tokens` (fcm_tokens.py): token thiết bị đăng ký theo user → push FCM
gửi theo từng máy, lọc bỏ vai trò bó hẹp / user bị khoá."""
from .schema import create_notif_table
from .queries import add_notification, get_notification, list_notifications, latest_id, prune_old
from .fcm_tokens import delete_tokens, eligible_rows, eligible_tokens, ensure_table, register_token

__all__ = [
    "create_notif_table",
    "add_notification",
    "get_notification",
    "list_notifications",
    "latest_id",
    "prune_old",
    "ensure_table",
    "register_token",
    "eligible_rows",
    "eligible_tokens",
    "delete_tokens",
]
