"""Bảng `notifications` (app.db) — nhật ký thông báo cho notification center webapp.

1 row = 1 thông báo (bình luận mới / ảnh mới / …), GHI CÙNG LÚC với push FCM
(server_app/notify.py) nên trung tâm thông báo trong app khớp với push. focus =
'<type>:<id>' để deep-link tới đúng phần trong đơn (#/order/<thread>?focus=...)."""
from __future__ import annotations


def create_notif_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT,               -- 'comment' | 'image' | ...
            title       TEXT,
            body        TEXT,
            thread_id   INTEGER,            -- đơn liên quan (nullable)
            focus       TEXT,               -- 'comment:123' cho deep-link (nullable)
            created_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_id ON notifications(id DESC)")
    conn.commit()
