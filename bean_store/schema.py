"""DDL KHO ĐẬU (app.db) — 4 bảng RIÊNG, không dính gì kho hàng hoá hiện tại:
`bean_places` (vị trí kho A/B…), `beans` (danh mục đậu), `bean_slips` (phiếu
nhập/xuất/điều chỉnh), `bean_moves` (dòng biến động — tồn = SUM(delta)).

ensure per-module (như area_store/disposal_store): CREATE TABLE IF NOT EXISTS gọi
từ route handler, KHÔNG qua db_migrate. Dùng bởi bean_store.*.
"""
from __future__ import annotations

_CREATE_PLACES = """
CREATE TABLE IF NOT EXISTS bean_places (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

_CREATE_BEANS = """
CREATE TABLE IF NOT EXISTS beans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    unit       TEXT DEFAULT 'kg',
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

# 1 phiếu = 1 loại thao tác, 1 vị trí kho, nhiều dòng đậu (bean_moves).
_CREATE_SLIPS = """
CREATE TABLE IF NOT EXISTS bean_slips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    place_id   INTEGER NOT NULL,
    partner    TEXT DEFAULT '',
    note       TEXT DEFAULT '',
    ymd        TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

# delta = số CỘNG vào tồn (+nhập / −xuất / ±điều chỉnh). quantity = số GHI trên
# phiếu (điều chỉnh: số đếm thực tế), before_qty = tồn trước khi điều chỉnh.
_CREATE_MOVES = """
CREATE TABLE IF NOT EXISTS bean_moves (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slip_id    INTEGER NOT NULL,
    bean_id    INTEGER NOT NULL,
    place_id   INTEGER NOT NULL,
    delta      REAL NOT NULL,
    quantity   REAL NOT NULL,
    before_qty REAL,
    note       TEXT DEFAULT ''
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_slip ON bean_moves(slip_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_bean ON bean_moves(bean_id, place_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_slips_day ON bean_slips(ymd)",
)


def ensure_tables(conn) -> None:
    conn.execute(_CREATE_PLACES)
    conn.execute(_CREATE_BEANS)
    conn.execute(_CREATE_SLIPS)
    conn.execute(_CREATE_MOVES)
    for sql in _IDX:
        conn.execute(sql)
