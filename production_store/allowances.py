"""PHỤ CẤP tiền cho thợ theo PHIẾU sản xuất (production_allowances) — app.db.

1 dòng = 1 (phiếu, thợ) → số tiền phụ cấp (ngoài tiền công theo sản lượng). NHẠY CẢM:
chỉ đọc/ghi qua endpoint đã chặn role văn phòng (server_app/production_wages).
Khoá theo (thread_id, worker_name) — tên thợ như trong báo cáo phiếu. Nối: utils.db.
"""
from __future__ import annotations

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_allowances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   INTEGER NOT NULL,
    worker_name TEXT    NOT NULL,
    amount      REAL    NOT NULL DEFAULT 0,
    updated_at  TEXT    DEFAULT (datetime('now')),
    updated_by  TEXT,
    UNIQUE(thread_id, worker_name)
);
"""
_INDEX = "CREATE INDEX IF NOT EXISTS idx_pallow_thread ON production_allowances(thread_id)"


def ensure_schema(conn) -> None:
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)


def get_allowances(conn, thread_id: int) -> dict:
    """{worker_name: amount} phụ cấp của 1 phiếu."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_name, amount FROM production_allowances WHERE thread_id = ?", (thread_id,)
    ).fetchall()
    return {r[0]: float(r[1] or 0) for r in rows}


def set_allowance(conn, thread_id: int, worker_name: str, amount: float, by: str = "") -> None:
    """Đặt phụ cấp cho 1 (phiếu, thợ). amount ≤ 0 → xoá dòng (coi như không có)."""
    ensure_schema(conn)
    name = (worker_name or "").strip()
    if not name:
        return
    with transaction(conn):
        if amount and amount > 0:
            conn.execute(
                "INSERT INTO production_allowances (thread_id, worker_name, amount, updated_at, updated_by) "
                "VALUES (?, ?, ?, datetime('now'), ?) "
                "ON CONFLICT(thread_id, worker_name) DO UPDATE SET amount=excluded.amount, "
                "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (thread_id, name, float(amount), by or ""),
            )
        else:
            conn.execute("DELETE FROM production_allowances WHERE thread_id = ? AND worker_name = ?", (thread_id, name))


def allowances_by_day_worker_product(conn, dfrom: str, dto: str) -> dict:
    """Σ phụ cấp theo (report_ymd, TÊN THỢ HIỆN HÀNH, MÃ SP HIỆN HÀNH) trong khoảng — để
    gắn phụ cấp vào ĐÚNG dòng SP của phiếu ở dashboard tiền công. Lấy ngày + SP + thợ (đã
    resolve id) của phiếu từ production_report_rows (phụ cấp gắn theo phiếu, khoá tên snapshot)."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT rr.ymd AS ymd, rr.worker AS worker, rr.code AS code, SUM(a.amount) AS allow "
        "FROM production_allowances a "
        "JOIN (SELECT DISTINCT t.thread_id, t.report_ymd AS ymd, t.worker_name AS wname, "
        "             COALESCE(w.name, t.worker_name) AS worker, COALESCE(pr.code, t.product_code) AS code "
        "      FROM production_report_rows t "
        "      LEFT JOIN products pr ON pr.id = t.product_id "
        "      LEFT JOIN production_workers w ON w.id = t.worker_id "
        "      WHERE t.report_ymd IS NOT NULL) rr "
        "  ON rr.thread_id = a.thread_id AND rr.wname = a.worker_name "
        "WHERE rr.ymd >= ? AND rr.ymd <= ? "
        "GROUP BY rr.ymd, rr.worker, rr.code",
        (dfrom, dto),
    ).fetchall()
    return {(r[0], r[1], r[2]): float(r[3] or 0) for r in rows}
