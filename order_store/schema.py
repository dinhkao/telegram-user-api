from __future__ import annotations
import contextlib
import logging
import os
import sqlite3

log = logging.getLogger("order_db")
from utils.paths import SHARED_DB_PATH
MIRROR_FIELDS = {"soan_hang": "soan", "giao_hang": "giao", "nop_tien": "nop", "nhan_tien": "nhan"}


def _get_connection():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


@contextlib.contextmanager
def transaction(conn):
    """Make a read-modify-write on the JSON blob atomic.

    Connections here run in autocommit (`isolation_level=None`), so a
    `get_order -> mutate dict -> _save_order` sequence spans two statements
    with no lock held between them — concurrent writers (the bot client, the
    Node process on the shared file) can interleave and lose the update. Wrap
    the sequence in `with transaction(conn):` to take a write lock up front
    (BEGIN IMMEDIATE) and commit atomically. Rolls back on exception.

    Re-entrancy-safe: if `conn` is already in a transaction, this is a no-op
    passthrough and the outermost context owns the commit.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
