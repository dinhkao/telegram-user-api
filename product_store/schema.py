"""Schema + migration bảng products (id INTEGER PK bất biến — mọi liên kết nội bộ
dùng id; code = nhãn UNIQUE đổi tự do) và product_code_history (nhật ký đổi mã,
kiêm alias mã cũ cho parser/route). Nối: utils.db."""
from __future__ import annotations

from utils.db import transaction

_products_cache: dict = {"data": None, "ts": 0}
_PRODUCTS_CACHE_TTL = 60

_PRODUCT_COLS_SQL = """
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            code          TEXT NOT NULL UNIQUE,
            name          TEXT,
            cost_price    INTEGER DEFAULT 0,
            note          TEXT,
            kv_id         INTEGER,
            kv_full_name  TEXT,
            kv_synced_at  TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            unit          TEXT DEFAULT 'cây',
            is_material   INTEGER DEFAULT 0,
            prod_mam      REAL,
            prod_luong    REAL,
            can_produce_directly INTEGER DEFAULT 1,
            can_package   INTEGER DEFAULT 0,
            min_stock     REAL DEFAULT 0,
            self_container INTEGER DEFAULT 0,
            can_sell      INTEGER DEFAULT 1,
            can_purchase  INTEGER DEFAULT 1
"""


def create_products_table(conn):
    conn.execute(f"CREATE TABLE IF NOT EXISTS products ({_PRODUCT_COLS_SQL})")
    _create_history_table(conn)
    conn.commit()


def _create_history_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_code_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            old_code    TEXT NOT NULL,
            new_code    TEXT NOT NULL,
            changed_at  TEXT NOT NULL,
            changed_by  TEXT DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pch_old ON product_code_history(old_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pch_pid ON product_code_history(product_id)")


def migrate_products_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "name" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN name TEXT")
    if "cost_price" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN cost_price INTEGER DEFAULT 0")
    if "note" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN note TEXT")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    if "kv_id" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN kv_id INTEGER")
    if "kv_full_name" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN kv_full_name TEXT")
    if "kv_synced_at" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN kv_synced_at TEXT")
    if "unit" not in columns:   # đơn vị đếm của SP (cây/kg/cái…) — mặc định 'cây'
        conn.execute("ALTER TABLE products ADD COLUMN unit TEXT DEFAULT 'cây'")
    if "is_material" not in columns:   # SP là NGUYÊN LIỆU (dùng làm thành phần đóng gói)
        conn.execute("ALTER TABLE products ADD COLUMN is_material INTEGER DEFAULT 0")
    if "prod_mam" not in columns:      # SX: số cây / 1 mâm (port từ SP_INFO config cứng)
        conn.execute("ALTER TABLE products ADD COLUMN prod_mam REAL")
    if "prod_luong" not in columns:    # SX: lượng mặc định (port từ SP_INFO)
        conn.execute("ALTER TABLE products ADD COLUMN prod_luong REAL")
    if "can_produce_directly" not in columns:   # SX TRỰC TIẾP được không (phiếu kind=san_xuat).
        conn.execute("ALTER TABLE products ADD COLUMN can_produce_directly INTEGER DEFAULT 1")  # backfill 0 cho SP có công thức ở db_migrate
    if "can_package" not in columns:   # ĐÓNG GÓI từ nguyên liệu được không (phiếu kind=dong_goi).
        conn.execute("ALTER TABLE products ADD COLUMN can_package INTEGER DEFAULT 0")  # backfill 1 cho SP đóng-gói-cũ/có công thức ở db_migrate
    if "min_stock" not in columns:      # tồn kho tối thiểu (ngưỡng cảnh báo)
        conn.execute("ALTER TABLE products ADD COLUMN min_stock REAL DEFAULT 0")
    if "self_container" not in columns:  # SP BẢN THÂN LÀ 1 thùng (KDXDB5/KGL5): mỗi thùng 1
        conn.execute("ALTER TABLE products ADD COLUMN self_container INTEGER DEFAULT 0")  # dòng, quantity=1, không có đơn vị chứa
    if "can_sell" not in columns:       # CÓ THỂ BÁN (hiện trong picker bán/hoá đơn)
        conn.execute("ALTER TABLE products ADD COLUMN can_sell INTEGER DEFAULT 1")
    if "can_purchase" not in columns:   # CÓ THỂ NHẬP (hiện trong picker phiếu nhập NCC)
        conn.execute("ALTER TABLE products ADD COLUMN can_purchase INTEGER DEFAULT 1")
    if "aux_required" not in columns:   # YÊU CẦU trừ NGUYÊN LIỆU PHỤ khi sản xuất (bật/tắt ở chi tiết SP)
        conn.execute("ALTER TABLE products ADD COLUMN aux_required INTEGER DEFAULT 1")
    if "id" not in columns:
        _rebuild_with_id(conn)
    _create_history_table(conn)
    conn.commit()
    _invalidate_products_cache()


def _rebuild_with_id(conn):
    """Bảng cũ có code TEXT PRIMARY KEY — SQLite không đổi PK tại chỗ được.
    Tạo bảng mới (id PK, code UNIQUE) → copy → swap, trong 1 transaction.
    id gán theo thứ tự mã (ổn định); chạy lại vô hại (guard 'id' ở migrate)."""
    with transaction(conn):
        conn.execute("DROP TABLE IF EXISTS products_new")
        conn.execute(f"CREATE TABLE products_new ({_PRODUCT_COLS_SQL})")
        conn.execute(
            "INSERT INTO products_new (code, name, cost_price, note, kv_id, kv_full_name, "
            "kv_synced_at, created_at, updated_at, unit, is_material, prod_mam, prod_luong) "
            "SELECT code, name, COALESCE(cost_price, 0), note, kv_id, kv_full_name, "
            "kv_synced_at, created_at, updated_at, COALESCE(unit, 'cây'), "
            "COALESCE(is_material, 0), prod_mam, prod_luong FROM products ORDER BY code"
        )
        conn.execute("DROP TABLE products")
        conn.execute("ALTER TABLE products_new RENAME TO products")


def _invalidate_products_cache():
    _products_cache["data"] = None
    _products_cache["ts"] = 0
