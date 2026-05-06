"""payment_db.py — Payments and debt SQLite read/write.

Shares order_db's connection model — uses the same app.db.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, UTC

from order_db import get_order_by_thread_id

log = logging.getLogger("payment_db")


def get_payments(conn, thread_id: int) -> list[dict]:
    """Get all payments for an order."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return []
    return order.get("payments", [])


def add_payment(conn, thread_id: int, payment: dict) -> tuple[bool, str]:
    """Add a payment record to an order. Returns (ok, message)."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"

    payments = order.get("payments", [])
    payment["id"] = f"payment_{len(payments)}_{int(datetime.now(UTC).timestamp())}"
    payment["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payments.append(payment)
    order["payments"] = payments
    order["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
        (json.dumps(order, ensure_ascii=False), order["updated_at"], thread_id),
    )
    conn.commit()

    method_label = payment.get("method", "unknown")
    amount = payment.get("amount", 0)
    return True, f"✅ Đã thêm thanh toán: {amount:,}đ ({method_label})"


def delete_payment_record(conn, thread_id: int, payment_id: str) -> tuple[bool, str]:
    """Delete a payment from an order. Returns (ok, message)."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"

    payments = order.get("payments", [])
    before = len(payments)
    order["payments"] = [p for p in payments if p.get("id") != payment_id]

    if len(order["payments"]) == before:
        return False, f"❌ Không tìm thấy payment: {payment_id}"

    order["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
        (json.dumps(order, ensure_ascii=False), order["updated_at"], thread_id),
    )
    conn.commit()
    return True, f"🗑️ Đã xóa payment: {payment_id}"


def calculate_debt(conn, thread_id: int) -> dict:
    """Calculate remaining debt for an order. Returns {total, paid, remaining}."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return {"total": 0, "paid": 0, "remaining": 0}

    total = order.get("tong_cong") or order.get("total") or 0
    payments = order.get("payments", [])
    paid = sum(p.get("amount", 0) for p in payments)

    return {
        "total": total,
        "paid": paid,
        "remaining": total - paid,
        "thread_id": thread_id,
    }


def get_all_debts(conn) -> list[dict]:
    """Get all orders with outstanding debt."""
    cur = conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"
    )
    debts = []
    for row in cur:
        try:
            order = json.loads(row["json"])
            total = order.get("tong_cong") or order.get("total") or 0
            payments = order.get("payments", [])
            paid = sum(p.get("amount", 0) for p in payments)
            remaining = total - paid
            if remaining > 0:
                debts.append({
                    "thread_id": row["thread_id"],
                    "customer": order.get("khach_hang", "N/A"),
                    "total": total,
                    "paid": paid,
                    "remaining": remaining,
                })
        except json.JSONDecodeError:
            continue
    return debts
