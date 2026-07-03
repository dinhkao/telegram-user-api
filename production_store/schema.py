from __future__ import annotations


def create_production_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_slips (
            thread_id   INTEGER PRIMARY KEY,
            channel_id  INTEGER,
            message_id  INTEGER,
            date        TEXT,
            date_code   TEXT,
            sp_name     TEXT,
            sp_mam      REAL,
            sp_luong    REAL,
            sx_target   INTEGER,
            total       REAL DEFAULT 0,
            numbers     TEXT,
            bang        TEXT,
            ghi_chu     TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def migrate_production_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(production_slips)").fetchall()}
    if "channel_id" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN channel_id INTEGER")
    if "message_id" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN message_id INTEGER")
    if "date" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN date TEXT")
    if "date_code" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN date_code TEXT")
    if "sp_name" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_name TEXT")
    if "sp_mam" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_mam REAL")
    if "sp_luong" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_luong REAL")
    if "sx_target" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sx_target INTEGER")
    if "total" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN total REAL DEFAULT 0")
    if "numbers" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN numbers TEXT")
    if "bang" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN bang TEXT")
    if "ghi_chu" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN ghi_chu TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    conn.commit()
