"""Schema bảng cashbox_transfers (app.db) — chuyển tiền tay giữa 2 két.

1 row = 1 lần chuyển (vd: Trang kết sổ cuối ngày, nộp tiền két cá nhân về két
văn phòng). Là dữ liệu DUY NHẤT của hệ két được lưu riêng — mọi thứ khác derive
từ blob đơn (xem cashbox_store.domain). Xoá = xoá mềm (deleted_at) để lịch sử
đối chiếu được. Kết nối: utils/db.py (get_connection), cashbox_store.queries.
"""
from __future__ import annotations

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS cashbox_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_box TEXT NOT NULL,
    to_box TEXT NOT NULL,
    amount INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    deleted_at TEXT
)
"""


def ensure_table(conn) -> None:
    conn.execute(CREATE_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cashbox_transfers_at ON cashbox_transfers(created_at)")
