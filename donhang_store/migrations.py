from __future__ import annotations
import logging

from vn import vn_normalize

log = logging.getLogger("donhang_db")


def migrate(conn) -> bool:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if not cols or "text_norm" in cols:
        return False
    log.info("migrating schema: adding text_norm column...")
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS messages_ai;
        DROP TRIGGER IF EXISTS messages_ad;
        DROP TRIGGER IF EXISTS messages_au;
        DROP TABLE IF EXISTS messages_fts;
        ALTER TABLE messages ADD COLUMN text_norm TEXT;
        """
    )
    rows = conn.execute("SELECT id, text, raw_text FROM messages").fetchall()
    conn.execute("BEGIN")
    try:
        for r in rows:
            conn.execute("UPDATE messages SET text_norm=? WHERE id=?", (vn_normalize((r[1] or "") + " " + (r[2] or "")), r[0]))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    log.info("migrated %d rows", len(rows))
    return True
