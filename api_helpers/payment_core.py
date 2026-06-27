from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from order_db import get_order_by_thread_id

log = logging.getLogger("payment_db")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _save(conn, order, thread_id: int) -> None:
    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
        (json.dumps(order, ensure_ascii=False), order["updated_at"], thread_id),
    )
    conn.commit()


def get_payments(conn, thread_id: int) -> list[dict]:
    order = get_order_by_thread_id(conn, thread_id)
    return [] if not order else order.get("payments", [])


def add_payment(conn, thread_id: int, payment: dict) -> tuple[bool, str]:
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"
    payments = order.get("payments", [])
    payment["id"] = f"payment_{len(payments)}_{int(datetime.now(UTC).timestamp())}"
    payment["created_at"] = _stamp()
    payments.append(payment)
    order["payments"] = payments
    order["updated_at"] = _stamp()
    _save(conn, order, thread_id)
    return True, f"✅ Đã thêm thanh toán: {payment.get('amount', 0):,}đ ({payment.get('method', 'unknown')})"


def delete_payment_record(conn, thread_id: int, payment_id: str) -> tuple[bool, str]:
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"
    payments = order.get("payments", [])
    order["payments"] = [p for p in payments if p.get("id") != payment_id]
    if len(order["payments"]) == len(payments):
        return False, f"❌ Không tìm thấy payment: {payment_id}"
    order["updated_at"] = _stamp()
    _save(conn, order, thread_id)
    return True, f"🗑️ Đã xóa payment: {payment_id}"


def calculate_debt(conn, thread_id: int) -> dict:
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return {"total": 0, "paid": 0, "remaining": 0}
    total = order.get("tong_cong") or order.get("total") or 0
    paid = sum(p.get("amount", 0) for p in order.get("payments", []))
    return {"total": total, "paid": paid, "remaining": total - paid, "thread_id": thread_id}


def get_all_debts(conn) -> list[dict]:
    debts = []
    for row in conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"):
        try:
            order = json.loads(row["json"])
        except json.JSONDecodeError:
            continue
        total = order.get("tong_cong") or order.get("total") or 0
        paid = sum(p.get("amount", 0) for p in order.get("payments", []))
        remaining = total - paid
        if remaining > 0:
            debts.append({"thread_id": row["thread_id"], "customer": order.get("khach_hang", "N/A"), "total": total, "paid": paid, "remaining": remaining})
    return debts

