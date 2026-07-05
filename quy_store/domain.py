"""Pure rules cho sổ quỹ — không IO, unit-test (tests/test_quy_domain.py).

Dùng chung bởi quy_store.queries (tính tổng khi list) và server_app.quy_routes
(validate input) để 2 nơi không lệch luật."""
from __future__ import annotations

RECEIPT_TYPES = ("thu", "chi")


def normalize_type(t) -> str | None:
    """'thu'/'chi' (hoặc alias +/-, income/expense) -> chuẩn; None nếu sai."""
    s = str(t or "").strip().lower()
    if s in ("thu", "income", "+", "in"):
        return "thu"
    if s in ("chi", "expense", "-", "out"):
        return "chi"
    return None


def parse_amount(v) -> int | None:
    """Số tiền > 0 (int). None nếu sai/không dương. Chấp nhận '1.000.000'/'1,000'."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = int(v)
    else:
        s = str(v or "").strip().replace(".", "").replace(",", "").replace(" ", "")
        if not s.lstrip("-").isdigit():
            return None
        n = int(s)
    return n if n > 0 else None


def signed(receipt: dict) -> int:
    """+amount cho thu, -amount cho chi (để cộng dồn ra số dư quỹ)."""
    amt = int(receipt.get("amount") or 0)
    return amt if receipt.get("type") == "thu" else -amt


def compute_summary(receipts) -> dict:
    """Tổng thu / chi / số dư (thu-chi) / đếm, trên 1 danh sách phiếu."""
    thu = sum(int(r.get("amount") or 0) for r in receipts if r.get("type") == "thu")
    chi = sum(int(r.get("amount") or 0) for r in receipts if r.get("type") == "chi")
    return {"thu": thu, "chi": chi, "balance": thu - chi, "count": len(list(receipts))}
