"""Lịch sử đổi giá từng SP trong bảng giá chung (bang_gia_moi). 1 row = 1 lần đổi
giá 1 SP (old→new, ai, khi nào). app.db, bảng price_history. Nối: utils.db."""
from __future__ import annotations

import time


def create_price_history_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id TEXT NOT NULL,
            sp TEXT NOT NULL,
            old_price INTEGER,          -- NULL = SP mới thêm
            new_price INTEGER,          -- NULL = SP bị xoá
            changed_by TEXT,
            changed_at INTEGER NOT NULL -- epoch ms
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history ON price_history(list_id, sp, changed_at DESC)")


def record_change(conn, list_id: str, sp: str, old_price, new_price, changed_by: str) -> None:
    conn.execute(
        "INSERT INTO price_history(list_id, sp, old_price, new_price, changed_by, changed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(list_id), sp, old_price, new_price, changed_by or "", int(time.time() * 1000)),
    )


def get_history(conn, list_id: str, sp: str | None = None, limit: int = 200) -> list[dict]:
    if sp:
        rows = conn.execute(
            "SELECT sp, old_price, new_price, changed_by, changed_at FROM price_history "
            "WHERE list_id = ? AND sp = ? ORDER BY changed_at DESC LIMIT ?",
            (str(list_id), sp, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sp, old_price, new_price, changed_by, changed_at FROM price_history "
            "WHERE list_id = ? ORDER BY changed_at DESC LIMIT ?",
            (str(list_id), limit),
        ).fetchall()
    return [dict(r) for r in rows]
