"""DDL KHO ĐẬU (app.db) — 5 bảng RIÊNG, không dính gì kho hàng hoá hiện tại:
`bean_places` (vị trí kho A/B…), `beans` (danh mục đậu), `bean_units` (đơn vị quy
đổi của từng loại đậu), `bean_slips` (phiếu nhập/xuất/điều chỉnh), `bean_moves`
(dòng biến động — tồn = SUM(delta), luôn theo ĐƠN VỊ GỐC).

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

# 1 row = 1 đơn vị quy đổi của 1 loại đậu. factor = 1 đơn vị này bằng bao nhiêu
# ĐƠN VỊ GỐC (beans.unit). Đơn vị gốc KHÔNG nằm ở bảng này.
_CREATE_UNITS = """
CREATE TABLE IF NOT EXISTS bean_units (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bean_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    factor     REAL NOT NULL,
    note       TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT ''
)
"""

# delta = số CỘNG vào tồn (+nhập / −xuất / ±điều chỉnh). quantity = số GHI trên
# phiếu (điều chỉnh: số đếm thực tế), before_qty = tồn trước khi điều chỉnh.
# CẢ BA đều theo ĐƠN VỊ GỐC. entered_qty/unit_name/unit_factor = snapshot cách
# người dùng đã gõ (vd "2 bao" với factor 50) để in lại đúng, KHÔNG dùng để tính.
_CREATE_MOVES = """
CREATE TABLE IF NOT EXISTS bean_moves (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slip_id     INTEGER NOT NULL,
    bean_id     INTEGER NOT NULL,
    place_id    INTEGER NOT NULL,
    delta       REAL NOT NULL,
    quantity    REAL NOT NULL,
    before_qty  REAL,
    entered_qty REAL,
    unit_name   TEXT DEFAULT '',
    unit_factor REAL DEFAULT 1,
    note        TEXT DEFAULT ''
)
"""

# Cột thêm sau (2026-08-10) — DB đã có bean_moves từ bản trước thì vá tại chỗ.
_MOVE_ADD_COLS = (
    ("entered_qty", "REAL"),
    ("unit_name", "TEXT DEFAULT ''"),
    ("unit_factor", "REAL DEFAULT 1"),
)

_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_slip ON bean_moves(slip_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_bean ON bean_moves(bean_id, place_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_slips_day ON bean_slips(ymd)",
    "CREATE INDEX IF NOT EXISTS idx_bean_units_bean ON bean_units(bean_id)",
)


def _add_missing_columns(conn) -> None:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(bean_moves)").fetchall()}
    for col, decl in _MOVE_ADD_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE bean_moves ADD COLUMN {col} {decl}")


def ensure_tables(conn) -> None:
    conn.execute(_CREATE_PLACES)
    conn.execute(_CREATE_BEANS)
    conn.execute(_CREATE_UNITS)
    conn.execute(_CREATE_SLIPS)
    conn.execute(_CREATE_MOVES)
    _add_missing_columns(conn)
    for sql in _IDX:
        conn.execute(sql)
