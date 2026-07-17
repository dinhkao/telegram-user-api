"""Pure inventory-box helpers (no IO) — SỐ GỌI thùng + gộp theo size.

Hệ số gọi (2026-07-08): mã thùng = 3 CHỮ SỐ '001'..'999' TOÀN KHO, cấp XOAY VÒNG
(tiếp từ số cấp gần nhất, nhảy qua số của thùng còn hàng/vô hiệu, hết 999 quay về
001). Ngoài kho chỉ cần hô "thùng 347" — không cần mã SP, không lẫn. Danh tính
bất biến của thùng là cột id (lịch sử móc theo id, số gọi tái dùng thoải mái).
Mã cũ kiểu 'K2L-001' (đếm theo SP, base36) vẫn parse được qua code_call_number —
thùng cũ giữ mã tới khi xuất hết. Unit-test ở tests/test_inventory_domain.py.
"""
from __future__ import annotations


# ─── Số gọi toàn kho ──────────────────────────────────────────────────────────
def call_code(n: int) -> str:
    """47 → '047' (3 chữ số, dễ đọc/hô ngoài kho)."""
    return f"{n:03d}"


def code_call_number(box_code: str) -> int:
    """Số gọi trong mã thùng, hệ MỚI lẫn CŨ: '047' → 47; 'K2L-00A' → 10 (đuôi
    base36 của mã cũ — để thùng cũ còn hàng vẫn CHIẾM số của nó trong vòng xoay,
    không cấp trùng lúc giao thời). 0 nếu không nhận ra / ngoài 1..999."""
    s = str(box_code or "").strip()
    if not s:
        return 0
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 999 else 0
    tail = s.rsplit("-", 1)[-1]
    try:
        n = int(tail, 36)
    except ValueError:
        return 0
    return n if 1 <= n <= 999 else 0


def next_call_numbers(last: int, taken, count: int) -> list[int]:
    """`count` số gọi kế tiếp — XOAY VÒNG: tiếp từ `last`+1 (999 quay về 001),
    nhảy qua `taken` (số của thùng còn hàng/vô hiệu — nhãn còn dán trên thùng).
    Xoay vòng tiến (không lấy lại số nhỏ nhất vừa trống) để số của thùng vừa hết
    hàng lâu bị tái dùng nhất — đỡ nhầm ngoài kho. Hết số → ValueError. Pure."""
    out: list[int] = []
    t = {n for n in taken if 1 <= n <= 999}
    n = last if 1 <= last <= 999 else 0
    for _ in range(count):
        for _ in range(999):
            n = n + 1 if n < 999 else 1
            if n not in t:
                break
        else:
            raise ValueError("Kho đã dùng hết 999 số thùng đang hoạt động")
        t.add(n)
        out.append(n)
    return out


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
