"""Schema kho thùng (inventory_boxes) — bảng trong shared app.db.

1 row = 1 thùng vật lý (mã tự sinh 'K2L-001'). Pool tồn kho gom theo product_code
(gộp mọi phiếu SX). Trạng thái: in_stock → allocated (xuất cho đơn) → shipped.
"""
from __future__ import annotations


def create_inventory_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_boxes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            product_code     TEXT NOT NULL,
            box_code         TEXT NOT NULL,
            quantity         REAL DEFAULT 0,
            status           TEXT DEFAULT 'in_stock',
            source_thread_id INTEGER,
            order_thread_id  INTEGER,
            note             TEXT,
            mfg_date         TEXT,
            disabled         INTEGER DEFAULT 0,
            disabled_reason  TEXT,
            created_at       TEXT DEFAULT (datetime('now')),
            created_by       TEXT,
            allocated_at     TEXT,
            allocated_by     TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inv_box_code ON inventory_boxes(box_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_product_status ON inventory_boxes(product_code, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_order ON inventory_boxes(order_thread_id)")
    # Vị trí kho (Kho A, Kho B…) — bảng riêng, thùng link qua place_id.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_places (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    # Đơn vị chứa (Thùng, Bọc, Cây, Kiện, Kệ…) — user tự định nghĩa; thùng link unit_id.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS inventory_units (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT OR IGNORE INTO inventory_units (name) VALUES ('Thùng')")  # mặc định
    conn.commit()


def migrate_inventory_table(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(inventory_boxes)").fetchall()}
    adds = {
        "order_thread_id": "INTEGER",
        "note": "TEXT",
        "mfg_date": "TEXT",
        "disabled": "INTEGER DEFAULT 0",
        "disabled_reason": "TEXT",
        "created_by": "TEXT",
        "allocated_at": "TEXT",
        "allocated_by": "TEXT",
        "place_id": "INTEGER",   # → inventory_places.id (vị trí kho)
        "unit_id": "INTEGER",    # → inventory_units.id (đơn vị chứa)
    }
    for name, typ in adds.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE inventory_boxes ADD COLUMN {name} {typ}")
    # đảm bảo bảng places/units tồn tại (DB cũ)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS inventory_places (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, note TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS inventory_units (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT OR IGNORE INTO inventory_units (name) VALUES ('Thùng')")
    conn.commit()
