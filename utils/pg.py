"""Wrapper psycopg trình bày bề mặt giống sqlite3.Connection mà app đang dùng.

Cho phép DB_ENGINE=postgres chạy CÙNG code hiện có (conn.execute(sql, params) với `?`,
row truy cập theo cả index lẫn tên, transaction()). Dịch SQL qua utils.sql_translate;
json_extract/json_set/json là SQL function phía PG (0001_init.sql). Chỉ dùng cho
app.db. Connects: utils.db (điểm switch), utils.sql_translate.

Bề mặt sqlite3 được mô phỏng (chỉ phần app dùng): execute/executemany/cursor/commit/
rollback/close, thuộc tính in_transaction, và Row hỗ trợ row[0] lẫn row["col"] + dict().
"""
from __future__ import annotations

from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool

from utils.sql_translate import translate

# Pool connection (giữ lại conn thay vì mở mới mỗi query). Mở conn PG tốn ~4ms
# (TCP+auth+docker); pool đưa xuống ~0.3ms/query — nhanh hơn cả SQLite cũ.
_pools: dict[str, ConnectionPool] = {}


def _get_pool(dsn: str) -> ConnectionPool:
    p = _pools.get(dsn)
    if p is None:
        # max_size lớn: app mở conn thoải mái không phải lúc nào cũng close() (thói quen
        # từ SQLite). __del__ của PgConnection trả conn về pool khi GC (bắt rò rỉ), nhưng
        # vẫn cần headroom cho conn giữ lâu (bot_core thread-local) + đỉnh đồng thời.
        p = ConnectionPool(
            dsn, min_size=2, max_size=64, max_idle=60.0, timeout=10.0,
            kwargs={"row_factory": _row_factory}, open=True,
        )
        _pools[dsn] = p
    return p


class Row:
    """Row lai: hỗ trợ index số (row[0]), tên (row['c']), và dict(row) — như sqlite3.Row."""

    __slots__ = ("_cols", "_vals", "_idx")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._idx = {c: i for i, c in enumerate(cols)}

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._vals[self._idx[k]]

    def get(self, k, default=None):
        i = self._idx.get(k)
        return self._vals[i] if i is not None else default

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)  # sqlite3.Row lặp qua GIÁ TRỊ

    def __len__(self):
        return len(self._vals)


def _row_factory(cursor):
    cols = [c.name for c in (cursor.description or [])]
    def make(values):
        return Row(cols, values)
    return make


class _Cursor:
    """Bọc cursor psycopg để bổ sung `lastrowid` (sqlite3 có, psycopg không).

    lastrowid = giá trị sequence cuối trong session (PG `lastval()`) — đúng cho INSERT
    vào cột IDENTITY (audit_events, order_chat_messages). Còn lại forward nguyên psycopg.
    """
    __slots__ = ("_cur", "_conn")

    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def __iter__(self):
        return iter(self._cur)

    @property
    def lastrowid(self):
        try:
            c = self._conn.cursor()
            c.execute("SELECT lastval()")
            r = c.fetchone()
            return r[0] if r else None
        except Exception:
            return None


class _Empty:
    """Kết quả rỗng cho PRAGMA no-op."""
    description = None
    rowcount = 0
    def fetchone(self): return None
    def fetchall(self): return []
    def __iter__(self): return iter(())


class PgConnection:
    def __init__(self, dsn: str, *, autocommit: bool = True):
        self._pool = _get_pool(dsn)
        self._conn = self._pool.getconn()
        self._closed = False
        if self._conn.autocommit != autocommit:
            if self._conn.info.transaction_status != TransactionStatus.IDLE:
                self._conn.rollback()
            self._conn.autocommit = autocommit

    # --- bề mặt sqlite3.Connection ---
    def execute(self, sql, params=()):
        s = sql.lstrip()
        up = s[:6].upper()
        if up == "PRAGMA":
            return self._pragma(s)
        cur = self._conn.cursor()
        cur.execute(translate(sql), tuple(params) if params else None)
        return _Cursor(cur, self._conn)

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(translate(sql), [tuple(p) for p in seq_of_params])
        return _Cursor(cur, self._conn)

    def executescript(self, script):
        # psycopg cho phép nhiều statement trong 1 execute khi không có param.
        cur = self._conn.cursor()
        cur.execute(translate(script))
        return cur

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # Trả conn về pool (không đóng thật) để tái dùng.
        if self._closed:
            return
        self._closed = True
        try:
            if not self._conn.autocommit and self._conn.info.transaction_status != TransactionStatus.IDLE:
                self._conn.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            pass

    def __del__(self):
        # Safety net: nếu caller quên close() (thói quen SQLite), GC trả conn về pool
        # để pool không cạn. Refcount GC gọi ngay khi biến ra khỏi scope.
        if not getattr(self, "_closed", True):
            self.close()

    @property
    def in_transaction(self) -> bool:
        return self._conn.info.transaction_status != TransactionStatus.IDLE

    # PRAGMA: table_info -> information_schema; còn lại no-op (WAL/busy_timeout vô nghĩa ở PG).
    def _pragma(self, s):
        import re
        m = re.match(r"PRAGMA\s+table_info\(\s*['\"]?(\w+)['\"]?\s*\)", s, re.IGNORECASE)
        if m:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT (ordinal_position-1) AS cid, column_name AS name, data_type AS type, "
                "0 AS notnull, NULL AS dflt_value, 0 AS pk "
                "FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",
                (m.group(1),),
            )
            return cur
        return _Empty()

    def __getattr__(self, name):
        return getattr(self._conn, name)
