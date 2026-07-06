"""Pure payment-domain logic — no IO, no KiotViet, no DB, no Telegram.

The pure decisions extracted from order_commands_v3._process_payment_core so they
can be unit-tested without hitting KiotViet or SQLite. The orchestration (network
+ DB writes) stays in the handler; it calls these. Phase 2 layering — see
docs/senior-review.md. Connects to: payment_store (adoption), consumed by
order_commands_v3._process_payment_core.
"""
from __future__ import annotations


def method_params(method: str) -> tuple[int | None, str]:
    """(kiotviet account_id, short label) for a payment method.
    Transfer -> (1, "CK"); Cash -> (None, "TM"). Matches the original inline logic."""
    account_id = 1 if method == "Transfer" else None
    method_label = "TM" if method == "Cash" else "CK"
    return account_id, method_label


def resolve_payment_target(order: dict | None, customer: dict | None) -> tuple:
    """Validate + derive the KiotViet payment target.

    Returns (kh_id_fb, kv_id, kh_name, error). `error` is a user-facing string
    when the payment can't proceed, else None. Fields are None when not yet
    known, mirroring the original's incremental result population.
    """
    if not order:
        return None, None, None, "Không tìm thấy đơn hàng"
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        return None, None, None, "Đơn hàng này chưa được gán khách hàng."
    if not customer or not customer.get("kh_id"):
        return kh_id_fb, None, None, "Không tìm thấy thông tin khách hàng hoặc ID KiotViet."
    kv_id = customer["kh_id"]
    kh_name = customer.get("name") or order.get("khach_hang") or str(kh_id_fb)
    return kh_id_fb, kv_id, kh_name, None


def build_payment_record(amount: int, method: str, kv_res: dict, actor_name: str,
                         *, old_debt: int | None = None, new_debt: int | None = None,
                         created_at: int | None = None) -> dict:
    """The SQLite payment row payload.

    old_debt/new_debt = công nợ khách TRƯỚC và SAU phiếu thu này (để section Thanh
    toán hiện 'nợ chuyển từ X sang Y'). created_at = epoch giây lúc tạo phiếu.
    Bản ghi cũ không có các field này → UI tự ẩn dòng."""
    rec = {"amount": amount, "method": method, "kiotvietData": kv_res, "createdBy": actor_name}
    if old_debt is not None:
        rec["old_debt"] = old_debt
    if new_debt is not None:
        rec["new_debt"] = new_debt
    if created_at is not None:
        rec["created_at"] = created_at
    return rec


def compute_debt(order: dict) -> dict:
    """Pure debt math for one order: total (tong_cong|total|0) minus sum of
    payment amounts. Returns {total, paid, remaining}. Callers add thread_id /
    customer. Single source for calculate_debt + get_all_debts."""
    total = order.get("tong_cong") or order.get("total") or 0
    paid = sum(p.get("amount", 0) for p in order.get("payments", []))
    return {"total": total, "paid": paid, "remaining": total - paid}
