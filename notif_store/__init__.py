"""notif_store — bảng `notifications` (app.db): nhật ký thông báo cho notification
center webapp. Ghi cùng lúc với push FCM (server_app/notify.py). API:
server_app/notify.py (ghi) + GET /api/notifications (đọc)."""
from .schema import create_notif_table
from .queries import add_notification, get_notification, list_notifications, latest_id, prune_old

__all__ = [
    "create_notif_table",
    "add_notification",
    "get_notification",
    "list_notifications",
    "latest_id",
    "prune_old",
]
