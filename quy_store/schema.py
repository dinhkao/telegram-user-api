"""Sổ quỹ (cash book) table schema -> shared SQLite (app.db).

1 row = 1 phiếu thu/chi. Nguồn 'manual' (tạo tay) hoặc 'order' (thanh toán tiền
mặt của 1 đơn — gắn order_thread_id + payment_id + khách). Xoá payment tiền mặt →
xoá phiếu thu gắn payment_id (queries.delete_by_payment)."""
from __future__ import annotations


def create_quy_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quy_receipts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            type             TEXT NOT NULL,            -- 'thu' | 'chi'
            amount           INTEGER NOT NULL,
            note             TEXT,
            source           TEXT DEFAULT 'manual',    -- 'manual' | 'order'
            order_thread_id  INTEGER,
            payment_id       TEXT,
            payment_batch_id TEXT,                     -- gộp 1 giao dịch thu nhiều đơn (bulk)
            customer_key     TEXT,
            customer_name    TEXT,
            created_by       TEXT,
            created_at       TEXT DEFAULT (datetime('now')),
            date             TEXT                       -- YYYY-MM-DD (giờ VN)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quy_date ON quy_receipts(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quy_order ON quy_receipts(order_thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quy_payment ON quy_receipts(payment_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quy_type ON quy_receipts(type)")
    conn.commit()


def migrate_quy_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(quy_receipts)").fetchall()}
    adds = {
        "note": "ALTER TABLE quy_receipts ADD COLUMN note TEXT",
        "source": "ALTER TABLE quy_receipts ADD COLUMN source TEXT DEFAULT 'manual'",
        "order_thread_id": "ALTER TABLE quy_receipts ADD COLUMN order_thread_id INTEGER",
        "payment_id": "ALTER TABLE quy_receipts ADD COLUMN payment_id TEXT",
        "payment_batch_id": "ALTER TABLE quy_receipts ADD COLUMN payment_batch_id TEXT",
        "customer_key": "ALTER TABLE quy_receipts ADD COLUMN customer_key TEXT",
        "customer_name": "ALTER TABLE quy_receipts ADD COLUMN customer_name TEXT",
        "created_by": "ALTER TABLE quy_receipts ADD COLUMN created_by TEXT",
        "created_at": "ALTER TABLE quy_receipts ADD COLUMN created_at TEXT",
        "date": "ALTER TABLE quy_receipts ADD COLUMN date TEXT",
    }
    for col, ddl in adds.items():
        if col not in columns:
            conn.execute(ddl)
    # Index cột payment_batch_id đặt Ở ĐÂY (sau khi cột chắc chắn tồn tại) — bảng cũ
    # gọi create_quy_table trước migrate nên không thể index cột chưa thêm.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quy_batch ON quy_receipts(payment_batch_id)")
    conn.commit()
