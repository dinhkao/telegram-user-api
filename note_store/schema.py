from __future__ import annotations


def create_note_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            thread_id   INTEGER PRIMARY KEY,
            text        TEXT,
            tags        TEXT,
            check_flag  INTEGER DEFAULT 0,
            del_flag    INTEGER DEFAULT 0,
            channel_id  INTEGER,
            message_id  INTEGER,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def migrate_note_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
    if "text" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN text TEXT")
    if "tags" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN tags TEXT")
    if "check_flag" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN check_flag INTEGER DEFAULT 0")
    if "del_flag" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN del_flag INTEGER DEFAULT 0")
    if "channel_id" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN channel_id INTEGER")
    if "message_id" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN message_id INTEGER")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE notes ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    conn.commit()
