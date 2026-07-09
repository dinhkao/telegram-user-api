"""Lịch sử đổi giá từng SP trong bảng giá chung (bang_gia_moi). 1 row = 1 lần đổi
giá 1 SP (old→new, ai, khi nào). Cột `sp` = MÃ tại thời điểm đổi (snapshot, dễ
đọc); `product_id` = danh tính bất biến — tra lịch sử 1 SP theo id nên đổi mã
xong lịch sử KHÔNG đứt. app.db, bảng price_history. Nối: utils.db, product_store."""
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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(price_history)").fetchall()}
    if "product_id" not in cols:  # migrate + backfill theo mã snapshot (idempotent)
        conn.execute("ALTER TABLE price_history ADD COLUMN product_id INTEGER")
        conn.execute(
            "UPDATE price_history SET product_id = "
            "(SELECT p.id FROM products p WHERE p.code = UPPER(TRIM(price_history.sp)))"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_pid ON price_history(list_id, product_id, changed_at DESC)")


def record_change(conn, list_id: str, sp: str, old_price, new_price, changed_by: str) -> None:
    from product_store import resolve_code
    prod = resolve_code(conn, sp)
    conn.execute(
        "INSERT INTO price_history(list_id, sp, product_id, old_price, new_price, changed_by, changed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(list_id), sp, (prod or {}).get("id"), old_price, new_price, changed_by or "",
         int(time.time() * 1000)),
    )


def get_history(conn, list_id: str, sp: str | None = None, limit: int = 200) -> list[dict]:
    """Lịch sử 1 bảng (sp=None) hoặc 1 SP. Tra theo DANH TÍNH khi mã resolve được
    (dòng cũ mang mã cũ vẫn ra); mã lạ fallback so mã snapshot."""
    if sp:
        from product_store import resolve_code
        prod = resolve_code(conn, sp)
        if prod:
            rows = conn.execute(
                "SELECT sp, old_price, new_price, changed_by, changed_at FROM price_history "
                "WHERE list_id = ? AND (product_id = ? OR (product_id IS NULL AND UPPER(sp) = ?)) "
                "ORDER BY changed_at DESC LIMIT ?",
                (str(list_id), prod["id"], prod["code"].upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sp, old_price, new_price, changed_by, changed_at FROM price_history "
                "WHERE list_id = ? AND UPPER(sp) = ? ORDER BY changed_at DESC LIMIT ?",
                (str(list_id), str(sp).upper().strip(), limit),
            ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sp, old_price, new_price, changed_by, changed_at FROM price_history "
            "WHERE list_id = ? ORDER BY changed_at DESC LIMIT ?",
            (str(list_id), limit),
        ).fetchall()
    return [dict(r) for r in rows]
