from __future__ import annotations


def create_bang_gia_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bang_gia_slips (
            thread_id   INTEGER PRIMARY KEY,
            name        TEXT,
            price_list  TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def migrate_bang_gia_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(bang_gia_slips)").fetchall()}
    if "name" not in columns:
        conn.execute("ALTER TABLE bang_gia_slips ADD COLUMN name TEXT")
    if "price_list" not in columns:
        conn.execute("ALTER TABLE bang_gia_slips ADD COLUMN price_list TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE bang_gia_slips ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    conn.commit()
