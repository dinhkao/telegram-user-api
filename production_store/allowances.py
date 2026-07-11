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


def allowances_by_day_worker(conn, dfrom: str, dto: str) -> dict:
    """Σ phụ cấp theo (report_ymd, worker_name) trong khoảng — cho dashboard tiền công.
    Lấy ngày của phiếu từ production_report_rows (phụ cấp gắn theo phiếu, không có ngày)."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT rr.report_ymd AS ymd, a.worker_name AS worker, SUM(a.amount) AS allow "
        "FROM production_allowances a "
        "JOIN (SELECT DISTINCT thread_id, report_ymd, worker_name FROM production_report_rows "
        "      WHERE report_ymd IS NOT NULL) rr "
        "  ON rr.thread_id = a.thread_id AND rr.worker_name = a.worker_name "
        "WHERE rr.report_ymd >= ? AND rr.report_ymd <= ? "
        "GROUP BY rr.report_ymd, a.worker_name",
        (dfrom, dto),
    ).fetchall()
    return {(r[0], r[1]): float(r[2] or 0) for r in rows}
