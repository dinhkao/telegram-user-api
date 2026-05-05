"""donhang_db.py — SQLite cache + FTS5 for #don_hang messages.

Schema:
- messages(id INT PK, date TEXT, text TEXT, raw_text TEXT, media TEXT, reply_to INT, updated_at REAL, deleted INT)
- messages_fts(text, raw_text) — FTS5 contentless mirror keyed by rowid=id
- meta(key TEXT PK, value TEXT) — backfill checkpoint, etc.

Usage:
    db = DonHangDB("donhang.db")
    db.upsert(msg_dict)
    db.mark_deleted(ids)
    db.search(query="cua", offset_id=0, limit=50)
"""
from __future__ import annotations
import logging
import sqlite3
import time
import threading
from typing import Optional

from vn import vn_normalize

log = logging.getLogger("donhang_db")

# text_norm = vn_normalize(text + ' ' + raw_text). FTS5 indexes text_norm only.
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    date        TEXT,
    text        TEXT,
    raw_text    TEXT,
    text_norm   TEXT,
    media       TEXT,
    reply_to    INTEGER,
    updated_at  REAL,
    deleted     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_id_desc ON messages(id DESC) WHERE deleted = 0;

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text_norm,
    content='messages', content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text_norm) VALUES (new.id, new.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text_norm)
        VALUES('delete', old.id, old.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text_norm)
        VALUES('delete', old.id, old.text_norm);
    INSERT INTO messages_fts(rowid, text_norm)
        VALUES (new.id, new.text_norm);
END;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class DonHangDB:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        needs_rebuild = self._migrate()
        self._conn.executescript(SCHEMA)
        if needs_rebuild:
            log.info("rebuilding FTS index...")
            self._conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
            log.info("FTS rebuild done")

    def _migrate(self) -> bool:
        """Migrate older schema (without text_norm) to new schema.
        Adds text_norm column, drops old FTS, repopulates text_norm.
        Returns True if FTS index needs rebuild after SCHEMA runs.
        """
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(messages)").fetchall()]
        if not cols:
            return False  # fresh DB; SCHEMA will create everything
        if "text_norm" in cols:
            return False  # already migrated
        log.info("migrating schema: adding text_norm column...")
        self._conn.executescript(
            """
            DROP TRIGGER IF EXISTS messages_ai;
            DROP TRIGGER IF EXISTS messages_ad;
            DROP TRIGGER IF EXISTS messages_au;
            DROP TABLE IF EXISTS messages_fts;
            ALTER TABLE messages ADD COLUMN text_norm TEXT;
            """
        )
        rows = self._conn.execute("SELECT id, text, raw_text FROM messages").fetchall()
        self._conn.execute("BEGIN")
        try:
            for r in rows:
                norm = vn_normalize((r[1] or "") + " " + (r[2] or ""))
                self._conn.execute("UPDATE messages SET text_norm=? WHERE id=?", (norm, r[0]))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        log.info("migrated %d rows", len(rows))
        return True

    # ── Mutations ────────────────────────────────────────────────────────────
    @staticmethod
    def _row_args(msg: dict) -> tuple:
        text = msg.get("text") or ""
        raw = msg.get("raw_text") or ""
        norm = vn_normalize(text + " " + raw)
        return (
            msg["id"],
            msg.get("date"),
            text,
            raw,
            norm,
            msg.get("media"),
            msg.get("reply_to"),
            time.time(),
        )

    _UPSERT_SQL = """INSERT INTO messages(id, date, text, raw_text, text_norm, media, reply_to, updated_at, deleted)
                     VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0)
                     ON CONFLICT(id) DO UPDATE SET
                         date=excluded.date,
                         text=excluded.text,
                         raw_text=excluded.raw_text,
                         text_norm=excluded.text_norm,
                         media=excluded.media,
                         reply_to=excluded.reply_to,
                         updated_at=excluded.updated_at,
                         deleted=0"""

    def upsert(self, msg: dict) -> None:
        """Insert or replace a single message."""
        with self._lock:
            self._conn.execute(self._UPSERT_SQL, self._row_args(msg))

    def upsert_many(self, msgs: list[dict]) -> int:
        if not msgs:
            return 0
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                for m in msgs:
                    self._conn.execute(self._UPSERT_SQL, self._row_args(m))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return len(msgs)

    def mark_deleted(self, ids: list[int]) -> int:
        if not ids:
            return 0
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE messages SET deleted=1, updated_at=? WHERE id IN ({','.join('?' * len(ids))})",
                (time.time(), *ids),
            )
            return cur.rowcount

    def delete_hard(self, ids: list[int]) -> int:
        if not ids:
            return 0
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})",
                tuple(ids),
            )
            return cur.rowcount

    # ── Reads ────────────────────────────────────────────────────────────────
    def page(self, offset_id: int = 0, limit: int = 50) -> list[dict]:
        """Return messages newest first; offset_id=0 means start from newest.
        offset_id > 0 returns messages with id < offset_id (next page).
        """
        if offset_id and offset_id > 0:
            sql = """SELECT * FROM messages
                     WHERE deleted = 0 AND id < ?
                     ORDER BY id DESC LIMIT ?"""
            rows = self._conn.execute(sql, (offset_id, limit)).fetchall()
        else:
            sql = """SELECT * FROM messages
                     WHERE deleted = 0
                     ORDER BY id DESC LIMIT ?"""
            rows = self._conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, offset_id: int = 0, limit: int = 50) -> list[dict]:
        """FTS5 search over Vietnamese-normalized text. Newest first.

        Query is vn_normalized so 'cua' matches 'Cửa', 'của', 'cưa', 'cừa'…
        """
        if not query.strip():
            return self.page(offset_id, limit)
        norm_q = vn_normalize(query)
        tokens = [t.replace('"', '""') for t in norm_q.split() if t.strip()]
        if not tokens:
            return self.page(offset_id, limit)
        fts_q = " ".join(f'"{t}"*' for t in tokens)

        if offset_id and offset_id > 0:
            sql = """SELECT m.* FROM messages_fts f
                     JOIN messages m ON m.id = f.rowid
                     WHERE messages_fts MATCH ? AND m.deleted = 0 AND m.id < ?
                     ORDER BY m.id DESC LIMIT ?"""
            args = (fts_q, offset_id, limit)
        else:
            sql = """SELECT m.* FROM messages_fts f
                     JOIN messages m ON m.id = f.rowid
                     WHERE messages_fts MATCH ? AND m.deleted = 0
                     ORDER BY m.id DESC LIMIT ?"""
            args = (fts_q, limit)
        rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        c = self._conn.execute("SELECT COUNT(*) AS n FROM messages WHERE deleted = 0").fetchone()
        d = self._conn.execute("SELECT COUNT(*) AS n FROM messages WHERE deleted = 1").fetchone()
        mn = self._conn.execute("SELECT MIN(id) AS i FROM messages WHERE deleted = 0").fetchone()
        mx = self._conn.execute("SELECT MAX(id) AS i FROM messages WHERE deleted = 0").fetchone()
        return {
            "total": c["n"],
            "deleted": d["n"],
            "min_id": mn["i"],
            "max_id": mx["i"],
            "meta": self.get_all_meta(),
        }

    # ── Meta ─────────────────────────────────────────────────────────────────
    def get_meta(self, key: str) -> Optional[str]:
        r = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_all_meta(self) -> dict:
        rows = self._conn.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def has_id(self, mid: int) -> bool:
        r = self._conn.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone()
        return r is not None
