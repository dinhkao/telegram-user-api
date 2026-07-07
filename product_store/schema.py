from __future__ import annotations

_products_cache: dict = {"data": None, "ts": 0}
_PRODUCTS_CACHE_TTL = 60


def create_products_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            code          TEXT PRIMARY KEY,
            name          TEXT,
            cost_price    INTEGER DEFAULT 0,
            note          TEXT,
            kv_id         INTEGER,
            kv_full_name  TEXT,
            kv_synced_at  TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            is_material   INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()


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
    conn.commit()


def _invalidate_products_cache():
    _products_cache["data"] = None
    _products_cache["ts"] = 0
