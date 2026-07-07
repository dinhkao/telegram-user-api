"""Pure inventory-box helpers (no IO) — mã thùng tự sinh + gộp theo size.

Logic thuần dùng chung cho inventory_store.queries + server_app.inventory_routes
nên bản Telegram và webapp không lệch nhau. Unit-test ở tests/test_inventory_domain.py.
"""
from __future__ import annotations


_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _to_base36(n: int) -> str:
    """Số nguyên → chuỗi base36 (0-9A-Z). 0 → '0'."""
    if n <= 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _B36[r] + out
    return out


def parse_box_seq(box_code: str, product_code: str) -> int:
    """Số thứ tự trong mã thùng (BASE36): 'K2L-00A' + 'K2L' → 10. 0 nếu không khớp.
    Base36 để mã gọn lâu: 3 ký tự chứa 46656 thùng/SP trước khi cần 4 ký tự."""
    prefix = f"{product_code}-"
    if not box_code or not box_code.startswith(prefix):
        return 0
    try:
        return int(box_code[len(prefix):], 36)   # base36; mã cũ (thập phân) vẫn parse duy nhất
    except ValueError:
        return 0


def format_box_code(product_code: str, seq: int) -> str:
    """'K2L' + 10 → 'K2L-00A' (base36, đệm 3 ký tự; tràn 46656 thì dài hơn)."""
    return f"{product_code}-{_to_base36(seq).rjust(3, '0')}"


def next_box_code(product_code: str, existing_codes) -> str:
    """Mã thùng kế tiếp theo product (tuần tự, tránh trùng số lớn nhất hiện có)."""
    mx = 0
    for c in existing_codes:
        mx = max(mx, parse_box_seq(c, product_code))
    return format_box_code(product_code, mx + 1)


def group_by_size(boxes) -> list[dict]:
    """Gộp thùng theo size (quantity) → [{quantity,count,total,box_codes}] tăng dần size."""
    buckets: dict = {}
    for b in boxes:
        q = b.get("quantity") or 0
        g = buckets.setdefault(q, {"quantity": q, "count": 0, "total": 0, "box_codes": []})
        g["count"] += 1
        g["total"] += q
        if b.get("box_code"):
            g["box_codes"].append(b["box_code"])
    return [buckets[k] for k in sorted(buckets)]


def summarize(boxes) -> dict:
    """Tổng tồn + số thùng + nhóm size cho 1 product (chỉ nên truyền thùng in_stock)."""
    groups = group_by_size(boxes)
    return {
        "total": sum(g["total"] for g in groups),
        "box_count": sum(g["count"] for g in groups),
        "groups": groups,
    }
