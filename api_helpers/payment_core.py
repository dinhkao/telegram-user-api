from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from order_db import get_order_by_thread_id

log = logging.getLogger("payment_db")

# NOTE: compute_debt is imported lazily inside the functions below. A top-level
# import would form a cycle: payment_store/__init__ -> queries -> this module.


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_payments(conn, thread_id: int) -> list[dict]:
    order = get_order_by_thread_id(conn, thread_id)
    return [] if not order else order.get("payments", [])


def add_payment(conn, thread_id: int, payment: dict) -> tuple[bool, str]:
    # uuid thay vì len(payments): tránh trùng id sau khi xoá 1 payment (len tái dùng chỉ số)
    payment["id"] = f"payment_{int(datetime.now(UTC).timestamp())}_{uuid.uuid4().hex[:8]}"
    payment["created_at"] = _stamp()
    # RMW blob NGUYÊN TỬ: BEGIN IMMEDIATE giữ lock từ read tới ghi → 2 thu tiền đồng
    # thời không nuốt phiếu. _save_order (order_db) KHÔNG commit trần nên re-entrant OK
    # (transaction bọc ngoài, nếu có, sở hữu commit).
    from order_db import _save_order
    from order_store.schema import transaction
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return False, "Không tìm thấy đơn hàng"
        payments = order.get("payments", [])
        payments.append(payment)
        order["payments"] = payments
        order["updated_at"] = _stamp()
        _save_order(conn, thread_id, order)
    return True, f"✅ Đã thêm thanh toán: {payment.get('amount', 0):,}đ ({payment.get('method', 'unknown')})"


def delete_payment_record(conn, thread_id: int, payment_id: str) -> tuple[bool, str]:
    from order_db import _save_order
    from order_store.schema import transaction
    with transaction(conn):
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return False, "Không tìm thấy đơn hàng"
        payments = order.get("payments", [])
        order["payments"] = [p for p in payments if p.get("id") != payment_id]
        if len(order["payments"]) == len(payments):
            return False, f"❌ Không tìm thấy payment: {payment_id}"
        order["updated_at"] = _stamp()
        _save_order(conn, thread_id, order)
    return True, f"🗑️ Đã xóa payment: {payment_id}"


def find_batch_thread_ids(conn, batch_id: str) -> list[int]:
    """thread_id của mọi đơn có 1 phiếu thu thuộc GIAO DỊCH gộp `batch_id` (bulk)."""
    rows = conn.execute(
        "SELECT DISTINCT o.thread_id tid FROM orders o, json_each(o.json,'$.payments') p"
        " WHERE json_extract(p.value,'$.payment_batch_id') = ? AND o.deleted_at IS NULL",
        (str(batch_id),),
    ).fetchall()
    return [r["tid"] for r in rows if r["tid"] is not None]


def remove_batch_payments(conn, batch_id: str) -> list[int]:
    """Gỡ mọi phiếu thu thuộc `batch_id` khỏi blob các đơn liên quan (nợ tự tính lại).

    Trả list thread_id đã đổi. Mỗi đơn RMW trong transaction (an toàn ghi đồng thời)."""
    from order_db import _save_order
    from order_store.schema import transaction
    changed: list[int] = []
    for tid in find_batch_thread_ids(conn, batch_id):
        with transaction(conn):
            order = get_order_by_thread_id(conn, int(tid))
            if not order:
                continue
            payments = order.get("payments", [])
            kept = [p for p in payments if p.get("payment_batch_id") != batch_id]
            if len(kept) == len(payments):
                continue
            order["payments"] = kept
            order["updated_at"] = _stamp()
            _save_order(conn, int(tid), order)   # KHÔNG commit — transaction bọc ngoài
            changed.append(int(tid))
    return changed


def calculate_debt(conn, thread_id: int) -> dict:
    from payment_store.domain import compute_debt
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return {"total": 0, "paid": 0, "remaining": 0}
    return {**compute_debt(order), "thread_id": thread_id}


def get_all_debts(conn) -> list[dict]:
    from payment_store.domain import compute_debt
    debts = []
    for row in conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"):
        try:
            order = json.loads(row["json"])
            d = compute_debt(order)  # trong try: 1 đơn dữ liệu lỗi không đánh sập cả báo cáo nợ
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        if d["remaining"] > 0:
            debts.append({"thread_id": row["thread_id"], "customer": order.get("khach_hang", "N/A"), **d})
    return debts

