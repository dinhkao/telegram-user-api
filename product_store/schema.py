from __future__ import annotations

_products_cache: dict = {"data": None, "ts": 0}
_PRODUCTS_CACHE_TTL = 60


def create_products_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            code        TEXT PRIMARY KEY,
            name        TEXT,
            cost_price  INTEGER DEFAULT 0,
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
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
    conn.commit()


def _invalidate_products_cache():
    _products_cache["data"] = None
    _products_cache["ts"] = 0
