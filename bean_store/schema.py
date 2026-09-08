"""DDL KHO ĐẬU (app.db) — 7 bảng RIÊNG, không dính gì kho hàng hoá hiện tại:
`bean_places` (vị trí kho A/B…), `beans` (danh mục đậu), `bean_units` (đơn vị quy
đổi của từng loại đậu), `bean_slips` (phiếu nhập/xuất/điều chỉnh), `bean_moves`
(dòng biến động — tồn = SUM(delta), luôn theo ĐƠN VỊ GỐC), `bean_stocktakes` +
`bean_stocktake_items` (PHIẾU KIỂM KHO: chụp sổ lúc bắt đầu, ghi số đếm, chốt →
sinh 1 phiếu điều chỉnh).

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
# kind='chuyen' thêm dest_place_id = KHO ĐÍCH (place_id = kho nguồn); loại khác NULL.
_CREATE_SLIPS = """
CREATE TABLE IF NOT EXISTS bean_slips (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,
    place_id      INTEGER NOT NULL,
    dest_place_id INTEGER,
    partner       TEXT DEFAULT '',
    note          TEXT DEFAULT '',
    ymd           TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    created_by    TEXT DEFAULT '',
    deleted_at    TEXT,
    deleted_by    TEXT
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

# Cột thêm sau trên bean_slips (2026-09-04 phiếu chuyển kho; 2026-09-08 kiểm kho:
# stocktake_id = phiếu điều chỉnh này do CHỐT phiếu kiểm kho nào sinh ra).
_SLIP_ADD_COLS = (
    ("dest_place_id", "INTEGER"),
    ("stocktake_id", "INTEGER"),
)

# PHIẾU KIỂM KHO: 1 phiếu = 1 kho, status draft → done | voided. Chụp sổ sách lúc tạo
# (expected_qty từng loại đậu), người đếm ghi counted_*; chốt (done) sinh 1 phiếu
# điều chỉnh (`slip_id`) với delta = đếm − sổ LÚC CHỤP (không đè biến động hợp lệ
# xảy ra sau khi đếm). Mỗi kho tối đa 1 nháp (partial unique index).
_CREATE_STOCKTAKES = """
CREATE TABLE IF NOT EXISTS bean_stocktakes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id     INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft',
    note         TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    created_by   TEXT DEFAULT '',
    updated_at   TEXT,
    updated_by   TEXT DEFAULT '',
    completed_at TEXT,
    completed_by TEXT DEFAULT '',
    voided_at    TEXT,
    voided_by    TEXT DEFAULT '',
    slip_id      INTEGER
)
"""

# 1 dòng = 1 loại đậu trong phiếu kiểm. expected_qty = sổ lúc chụp (ĐƠN VỊ GỐC);
# counted_qty = số đếm quy về gốc, NULL = chưa đếm (chốt sẽ BỎ QUA dòng này);
# counted_bulk/loose/unit_* = số THÔ người đếm gõ ("3 bao + 12 kg") để in lại đúng.
_CREATE_STOCKTAKE_ITEMS = """
CREATE TABLE IF NOT EXISTS bean_stocktake_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stocktake_id  INTEGER NOT NULL,
    bean_id       INTEGER NOT NULL,
    expected_qty  REAL NOT NULL DEFAULT 0,
    counted_qty   REAL,
    counted_bulk  REAL,
    counted_loose REAL,
    unit_id       INTEGER,
    unit_name     TEXT DEFAULT '',
    unit_factor   REAL DEFAULT 1,
    note          TEXT DEFAULT '',
    counted_at    TEXT,
    counted_by    TEXT DEFAULT '',
    UNIQUE(stocktake_id, bean_id)
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_slip ON bean_moves(slip_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_moves_bean ON bean_moves(bean_id, place_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_slips_day ON bean_slips(ymd)",
    "CREATE INDEX IF NOT EXISTS idx_bean_units_bean ON bean_units(bean_id)",
    "CREATE INDEX IF NOT EXISTS idx_bean_stocktakes_place ON bean_stocktakes(place_id, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_bean_stocktake_draft ON bean_stocktakes(place_id) "
    "WHERE status = 'draft'",
)


def _add_missing_columns(conn) -> None:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(bean_moves)").fetchall()}
    for col, decl in _MOVE_ADD_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE bean_moves ADD COLUMN {col} {decl}")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(bean_slips)").fetchall()}
    for col, decl in _SLIP_ADD_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE bean_slips ADD COLUMN {col} {decl}")


def ensure_tables(conn) -> None:
    conn.execute(_CREATE_PLACES)
    conn.execute(_CREATE_BEANS)
    conn.execute(_CREATE_UNITS)
    conn.execute(_CREATE_SLIPS)
    conn.execute(_CREATE_MOVES)
    conn.execute(_CREATE_STOCKTAKES)
    conn.execute(_CREATE_STOCKTAKE_ITEMS)
    _add_missing_columns(conn)
    for sql in _IDX:
        conn.execute(sql)
