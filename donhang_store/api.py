from __future__ import annotations
import logging
import sqlite3
import threading

from .migrations import migrate
from .reads import get_all_meta, get_meta, has_id, page, search, set_meta, stats
from .schema import SCHEMA
from .writes import delete_hard, mark_deleted, upsert, upsert_many

log = logging.getLogger("donhang_db")


class DonHangDB:
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

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        needs_rebuild = migrate(self._conn)
        self._conn.executescript(SCHEMA)
        if needs_rebuild:
            log.info("rebuilding FTS index...")
            self._conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
            log.info("FTS rebuild done")

    upsert = upsert
    upsert_many = upsert_many
    mark_deleted = mark_deleted
    delete_hard = delete_hard
    page = page
    search = search
    stats = stats
    get_meta = get_meta
    set_meta = set_meta
    get_all_meta = get_all_meta
    has_id = has_id
