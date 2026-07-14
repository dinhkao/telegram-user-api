"""Thanh toán phiếu NHẬP HÀNG từ két tiền — cột JSON `payments` trên purchase_slips.

1 payment = {"id": int (epoch ms), "amount": int, "box": "user:tri", "by": username,
"at": ISO +07:00}. Ghi = read-modify-write NGUYÊN TỬ (utils.db.transaction), chặn
trả quá phần còn nợ ngay trong transaction. Tiền RA khỏi hệ két (két → NCC) —
cashbox_store.service derive các payment này thành movement. Xoá payment = admin
(gỡ khỏi list, két tính lại). Nối: purchase_store (schema), utils.db,
cashbox_store.service (đọc), server_app/purchase_routes.py (API).
"""
from __future__ import annotations

import json
import time

from utils.db import transaction


def _parse(raw) -> list[dict]:
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def paid_total(payments: list[dict]) -> int:
    total = 0
    for p in payments if isinstance(payments, list) else []:
        try:
            total += int(round(float(p.get("amount") or 0)))
        except (TypeError, ValueError):
            pass
    return total


def add_purchase_payment(conn, purchase_id: int, amount: int, box: str, by: str) -> tuple[dict | None, str]:
    """Thêm 1 lần trả tiền NCC. Trả (payment, "") hoặc (None, lý_do_VN).
    Kiểm tra CÒN NỢ trong cùng transaction — 2 lần trả đồng thời không vượt tổng."""
    from purchase_store import _now_vn, ensure_purchases_schema
    ensure_purchases_schema(conn)
    amount = int(amount)
    if amount <= 0:
        return None, "Số tiền phải > 0"
    with transaction(conn):
        r = conn.execute(
            "SELECT total, payments, deleted_at FROM purchase_slips WHERE id = ?",
            (purchase_id,)).fetchone()
        if not r or r["deleted_at"]:
            return None, "Không tìm thấy phiếu nhập"
        pays = _parse(r["payments"])
        remaining = int(round(float(r["total"] or 0))) - paid_total(pays)
        if amount > remaining:
            return None, f"Phiếu chỉ còn nợ {remaining:,}đ — không nhận {amount:,}đ".replace(",", ".")
        pid = int(time.time() * 1000)
        while any(p.get("id") == pid for p in pays):
            pid += 1
        rec = {"id": pid, "amount": amount, "box": box, "by": by or "", "at": _now_vn()}
        pays.append(rec)
        conn.execute("UPDATE purchase_slips SET payments = ? WHERE id = ?",
                     (json.dumps(pays, ensure_ascii=False), purchase_id))
    return rec, ""


def delete_purchase_payment(conn, purchase_id: int, payment_id: int) -> dict | None:
    """Gỡ 1 lần trả (admin). Trả payment đã gỡ hoặc None nếu không có."""
    from purchase_store import ensure_purchases_schema
    ensure_purchases_schema(conn)
    with transaction(conn):
        r = conn.execute(
            "SELECT payments FROM purchase_slips WHERE id = ?", (purchase_id,)).fetchone()
        if not r:
            return None
        pays = _parse(r["payments"])
        removed = next((p for p in pays if p.get("id") == payment_id), None)
        if not removed:
            return None
        pays = [p for p in pays if p.get("id") != payment_id]
        conn.execute("UPDATE purchase_slips SET payments = ? WHERE id = ?",
                     (json.dumps(pays, ensure_ascii=False), purchase_id))
    return removed


def payments_for_cashbox(conn) -> list[dict]:
    """Mọi payment của phiếu nhập CHƯA XOÁ (kèm tên NCC) — nguồn derive két."""
    from purchase_store import ensure_purchases_schema
    ensure_purchases_schema(conn)
    from supplier_store import ensure_suppliers_schema
    ensure_suppliers_schema(conn)
    out = []
    for r in conn.execute(
            "SELECT p.id, p.payments, s.name AS supplier_name FROM purchase_slips p"
            " LEFT JOIN suppliers s ON s.id = p.supplier_id"
            " WHERE p.deleted_at IS NULL AND p.payments IS NOT NULL AND p.payments != '[]'"):
        out.append({"purchase_id": r["id"], "supplier_name": r["supplier_name"] or "",
                    "payments": _parse(r["payments"])})
    return out
