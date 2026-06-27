from __future__ import annotations
import time

from .serialization import _row_args


def upsert(self, msg: dict) -> None:
    with self._lock:
        self._conn.execute(self._UPSERT_SQL, _row_args(msg))


def upsert_many(self, msgs: list[dict]) -> int:
    if not msgs:
        return 0
    with self._lock:
        self._conn.execute("BEGIN")
        try:
            for m in msgs:
                self._conn.execute(self._UPSERT_SQL, _row_args(m))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
    return len(msgs)


def mark_deleted(self, ids: list[int]) -> int:
    if not ids:
        return 0
    with self._lock:
        cur = self._conn.execute(f"UPDATE messages SET deleted=1, updated_at=? WHERE id IN ({','.join('?' * len(ids))})", (time.time(), *ids))
        return cur.rowcount


def delete_hard(self, ids: list[int]) -> int:
    if not ids:
        return 0
    with self._lock:
        cur = self._conn.execute(f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))
        return cur.rowcount
