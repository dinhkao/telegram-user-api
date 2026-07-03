"""Pure inventory-box helpers (no IO) — mã thùng tự sinh + gộp theo size.

Logic thuần dùng chung cho inventory_store.queries + server_app.inventory_routes
nên bản Telegram và webapp không lệch nhau. Unit-test ở tests/test_inventory_domain.py.
"""
from __future__ import annotations


def parse_box_seq(box_code: str, product_code: str) -> int:
    """Số thứ tự trong mã thùng: 'K2L-007' + 'K2L' → 7. 0 nếu không khớp."""
    prefix = f"{product_code}-"
    if not box_code or not box_code.startswith(prefix):
        return 0
    try:
        return int(box_code[len(prefix):])
    except ValueError:
        return 0


def format_box_code(product_code: str, seq: int) -> str:
    """'K2L' + 7 → 'K2L-007' (đệm 3 số, tràn thì dài hơn)."""
    return f"{product_code}-{seq:03d}"


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
