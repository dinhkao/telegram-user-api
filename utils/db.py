"""Cổng kết nối SQLite duy nhất — điểm swap engine cho migration Postgres.

Mọi store trỏ `app.db` (SHARED_DB_PATH) lấy connection TỪ ĐÂY thay vì tự
`sqlite3.connect`. Gom về một chỗ để: (1) khi chuyển sang Postgres chỉ sửa 1 file,
(2) cấu hình (WAL, busy_timeout, autocommit, readonly) nhất quán và tường minh.

`get_connection()` có đủ tham số để tái tạo Y HỆT từng biến thể đang tồn tại:
- mặc định: autocommit (isolation_level=None), WAL, Row factory, busy_timeout=5000.
- `readonly=True`: mở `?mode=ro` (what_data chỉ đọc).
- `autocommit=False`: dùng transaction ngầm của sqlite3 (chat_log, orders_db —
  vốn không đặt isolation_level).

Depends: utils.paths (SHARED_DB_PATH). Không import gì trong project khác → an toàn
import mọi nơi, không cycle. Connects to: order_store, chat_log, server_app.orders_db,
command_handlers.* — các store trên app.db.

NGOÀI phạm vi cổng này (giữ connect riêng, ngữ nghĩa khác): donhang_store (DB khác),
bot_core.session_store (bot_sessions.db), bot_core.db (thread-local + migrate +
foreign_keys), audit.db (path tham số). Xem docs/postgres-migration.md Phase A.
"""
from __future__ import annotations

import contextlib
import os
import sqlite3

from utils.paths import SHARED_DB_PATH

# Công tắc engine: 'sqlite' (mặc định) | 'postgres'. Đổi qua env, KHÔNG sửa code.
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").strip().lower()
IS_POSTGRES = DB_ENGINE in ("postgres", "postgresql", "pg")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://letrang:letrang@localhost:5432/app")


def get_connection(
    path: str = SHARED_DB_PATH,
    *,
    readonly: bool = False,
    autocommit: bool = True,
    busy_timeout: int = 5000,
):
    """Mở connection tới app.db — SQLite hoặc Postgres tùy DB_ENGINE.

    Postgres (DB_ENGINE=postgres): trả `utils.pg.PgConnection` (bề mặt giống sqlite3,
    dịch SQL qua utils.sql_translate). `path`/`readonly`/`busy_timeout` bỏ qua.

    SQLite (mặc định): connection cấu hình chuẩn (WAL + Row + busy_timeout).
    autocommit=True  → isolation_level=None (cần `transaction()` cho RMW nguyên tử).
    autocommit=False → isolation_level="" (transaction ngầm sqlite3 — giữ hành vi cũ).
    """
    if IS_POSTGRES:
        from utils.pg import PgConnection
        return PgConnection(DATABASE_URL, autocommit=autocommit)
    isolation = None if autocommit else ""
    if readonly:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, check_same_thread=False, isolation_level=isolation
        )
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=isolation)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout)}")
    return conn


@contextlib.contextmanager
def transaction(conn):
    """Make a read-modify-write on the JSON blob atomic.

    Connections here run in autocommit (`isolation_level=None`), so a
    `get_order -> mutate dict -> _save_order` sequence spans two statements
    with no lock held between them — concurrent writers on the shared file can
    interleave and lose the update. Wrap the sequence in `with transaction(conn):`
    to take a write lock up front (BEGIN IMMEDIATE) and commit atomically. Rolls
    back on exception.

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
