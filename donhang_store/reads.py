from __future__ import annotations

from vn import vn_normalize


def page(self, offset_id: int = 0, limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM messages WHERE deleted = 0" + (" AND id < ?" if offset_id and offset_id > 0 else "") + " ORDER BY id DESC LIMIT ?"
    rows = self._conn.execute(sql, (offset_id, limit) if offset_id and offset_id > 0 else (limit,)).fetchall()
    return [dict(r) for r in rows]


def search(self, query: str, offset_id: int = 0, limit: int = 50) -> list[dict]:
    if not query.strip():
        return page(self, offset_id, limit)
    tokens = [t.replace('"', '""') for t in vn_normalize(query).split() if t.strip()]
    if not tokens:
        return page(self, offset_id, limit)
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
    return [dict(r) for r in self._conn.execute(sql, args).fetchall()]


def stats(self) -> dict:
    c = self._conn.execute("SELECT COUNT(*) AS n FROM messages WHERE deleted = 0").fetchone()
    d = self._conn.execute("SELECT COUNT(*) AS n FROM messages WHERE deleted = 1").fetchone()
    mn = self._conn.execute("SELECT MIN(id) AS i FROM messages WHERE deleted = 0").fetchone()
    mx = self._conn.execute("SELECT MAX(id) AS i FROM messages WHERE deleted = 0").fetchone()
    return {"total": c["n"], "deleted": d["n"], "min_id": mn["i"], "max_id": mx["i"], "meta": self.get_all_meta()}


def get_meta(self, key: str):
    r = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def set_meta(self, key: str, value: str) -> None:
    with self._lock:
        self._conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_all_meta(self) -> dict:
    return {r["key"]: r["value"] for r in self._conn.execute("SELECT key, value FROM meta").fetchall()}


def has_id(self, mid: int) -> bool:
    return self._conn.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone() is not None
