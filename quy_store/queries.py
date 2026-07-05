"""Sổ quỹ CRUD trên bảng quy_receipts (app.db). Transaction + IO; luật thuần ở
quy_store.domain. Số dư quỹ tính bằng SUM(thu)-SUM(chi) trên toàn bộ (không phân
trang) để header luôn đúng."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

_VN_TZ = timezone(timedelta(hours=7))

_COLUMNS = (
    "id", "type", "amount", "note", "source", "order_thread_id",
    "payment_id", "customer_key", "customer_name", "created_by", "created_at", "date",
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _vn_date() -> str:
    return datetime.now(_VN_TZ).strftime("%Y-%m-%d")


def create_receipt(
    conn,
    *,
    type: str,
    amount: int,
    note: str = "",
    source: str = "manual",
    order_thread_id: int | None = None,
    payment_id: str | None = None,
    customer_key: str | None = None,
    customer_name: str | None = None,
    created_by: str = "",
) -> dict:
    """Chèn 1 phiếu; trả về row dict (kèm id mới)."""
    cur = conn.execute(
        """
        INSERT INTO quy_receipts
            (type, amount, note, source, order_thread_id, payment_id,
             customer_key, customer_name, created_by, created_at, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (type, int(amount), note or "", source, order_thread_id, payment_id,
         customer_key, customer_name, created_by, _now_iso(), _vn_date()),
    )
    conn.commit()
    return get_receipt(conn, cur.lastrowid)


def get_receipt(conn, receipt_id) -> dict | None:
    row = conn.execute("SELECT * FROM quy_receipts WHERE id = ?", (receipt_id,)).fetchone()
    return dict(row) if row else None


def _where(type_filter: str | None, q: str | None):
    clauses, params = [], []
    if type_filter in ("thu", "chi"):
        clauses.append("type = ?")
        params.append(type_filter)
    if q:
        clauses.append("(note LIKE ? OR customer_name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def list_receipts(conn, *, limit=20, offset=0, type_filter=None, q=None) -> list[dict]:
    where, params = _where(type_filter, q)
    rows = conn.execute(
        f"SELECT * FROM quy_receipts{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def count_receipts(conn, *, type_filter=None, q=None) -> int:
    where, params = _where(type_filter, q)
    row = conn.execute(f"SELECT COUNT(*) AS c FROM quy_receipts{where}", params).fetchone()
    return int(row["c"]) if row else 0


def summary(conn) -> dict:
    """Tổng thu / chi / số dư trên TOÀN sổ (không lọc trang)."""
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN type='thu' THEN amount ELSE 0 END), 0) AS thu,
            COALESCE(SUM(CASE WHEN type='chi' THEN amount ELSE 0 END), 0) AS chi,
            COUNT(*) AS count
        FROM quy_receipts
        """
    ).fetchone()
    thu, chi, cnt = int(row["thu"]), int(row["chi"]), int(row["count"])
    return {"thu": thu, "chi": chi, "balance": thu - chi, "count": cnt}


def list_by_order(conn, order_thread_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM quy_receipts WHERE order_thread_id = ? ORDER BY id DESC",
        (order_thread_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_receipt(conn, receipt_id) -> bool:
    cur = conn.execute("DELETE FROM quy_receipts WHERE id = ?", (receipt_id,))
    conn.commit()
    return cur.rowcount > 0


def delete_by_payment(conn, payment_id: str) -> int:
    """Xoá phiếu thu gắn 1 payment (khi payment tiền mặt của đơn bị xoá)."""
    cur = conn.execute("DELETE FROM quy_receipts WHERE payment_id = ?", (payment_id,))
    conn.commit()
    return cur.rowcount
