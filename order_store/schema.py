from __future__ import annotations
import logging
import os
import sqlite3

log = logging.getLogger("order_db")
SHARED_DB_PATH = os.path.expanduser(os.getenv("SHARED_DB_PATH", "~/letrang-db/app.db"))
MIRROR_FIELDS = {"soan_hang": "soan", "giao_hang": "giao", "nop_tien": "nop", "nhan_tien": "nhan"}


def _get_connection():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn
