"""Bảng `notifications` (app.db) — nhật ký thông báo cho notification center webapp.

1 row = 1 thông báo (bình luận mới / ảnh mới / …), GHI CÙNG LÚC với push FCM
(server_app/notify.py) nên trung tâm thông báo trong app khớp với push. focus =
'<type>:<id>' để deep-link tới đúng phần trong đơn (#/order/<thread>?focus=...).
route = hash webapp cho thông báo KHÔNG thuộc đơn hàng (vd phiếu kho đậu
'#/kho-dau/phieu/12') — có route thì client mở thẳng route đó."""
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
            image_id    INTEGER,            -- ảnh liên quan → thumbnail ở popup/FCM (nullable)
            route       TEXT,               -- hash webapp cho thông báo ngoài đơn (nullable)
            created_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_id ON notifications(id DESC)")
    _migrate(conn)
    conn.commit()


def _migrate(conn):
    """Thêm cột mới cho bảng cũ (idempotent). image_id: thumbnail thông báo ảnh.
    route: deep-link cho thông báo không thuộc đơn hàng (kho đậu…)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notifications)").fetchall()}
    if "image_id" not in cols:
        conn.execute("ALTER TABLE notifications ADD COLUMN image_id INTEGER")
    if "route" not in cols:
        conn.execute("ALTER TABLE notifications ADD COLUMN route TEXT")
