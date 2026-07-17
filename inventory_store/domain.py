"""Pure inventory-box helpers (no IO) — SỐ GỌI thùng + gộp theo size.

Hệ số gọi (2026-07-08; MỞ RỘNG BLOCK CHỮ 2026-07-17): mã thùng TOÀN KHO, cấp
XOAY VÒNG trên 27 block × 999 = 26.973 số: '001'..'999' (block 0, không tiền tố)
→ 'A001'..'A999' → 'B001' … 'Z999' rồi quay về '001'. Tiếp từ số cấp gần nhất,
nhảy qua số của thùng còn hàng/vô hiệu. Ngoài kho chỉ hô "thùng 347" / "thùng A
ba-bốn-bảy" — không cần mã SP, không lẫn. Danh tính bất biến của thùng là cột id
(lịch sử móc theo id, số gọi tái dùng thoải mái). Mã cũ kiểu 'K2L-001' (đếm theo
SP, base36) vẫn parse được qua code_call_number — thùng cũ giữ mã tới khi xuất
hết. Unit-test ở tests/test_inventory_domain.py.
"""
from __future__ import annotations

import re

# 27 block (001–999 trần + A–Z) × 999 số/block = 26.973 số gọi.
CALL_MAX = 27 * 999

_LETTER_CODE = re.compile(r"^([A-Za-z])(\d{3})$")   # mã mới block chữ: 'A047'


# ─── Số gọi toàn kho ──────────────────────────────────────────────────────────
def call_block(n: int) -> str:
    """Tiền tố block của số gọi: 47 → '' (block 001–999); 1046 → 'A'; 26973 → 'Z'.
    Ngoài 1..CALL_MAX → ''."""
    if not (1 <= n <= CALL_MAX):
        return ""
    block = (n - 1) // 999
    return chr(ord("A") + block - 1) if block else ""


def call_code(n: int) -> str:
    """47 → '047'; 1046 → 'A047' (block chữ sau 999 — vẫn dễ đọc/hô ngoài kho).
    Ngoài 1..CALL_MAX: giữ hành vi cũ, format số 3 chữ số trần (không raise)."""
    if 1000 <= n <= CALL_MAX:
        pos = (n - 1) % 999 + 1
        return f"{call_block(n)}{pos:03d}"
    return f"{n:03d}"


def code_call_number(box_code: str) -> int:
    """Số gọi trong mã thùng, hệ MỚI lẫn CŨ: '047' → 47; 'A047' → 1046 (block chữ
    — đúng 1 chữ + 3 số, chữ thường chuẩn hoá hoa, 'A000' loại); 'K2L-00A' → 10
    (đuôi base36 của mã cũ — để thùng cũ còn hàng vẫn CHIẾM số của nó trong vòng
    xoay, không cấp trùng lúc giao thời). 0 nếu không nhận ra / ngoài dải."""
    s = str(box_code or "").strip()
    if not s:
        return 0
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 999 else 0
    m = _LETTER_CODE.match(s)
    if m:
        pos = int(m.group(2))
        if not (1 <= pos <= 999):
            return 0                       # 'A000' — vị trí trong block phải 1..999
        block = ord(m.group(1).upper()) - ord("A") + 1
        return block * 999 + pos
    tail = s.rsplit("-", 1)[-1]
    try:
        n = int(tail, 36)
    except ValueError:
        return 0
    return n if 1 <= n <= 999 else 0


def next_call_numbers(last: int, taken, count: int) -> list[int]:
    """`count` số gọi kế tiếp — XOAY VÒNG trên 1..CALL_MAX: tiếp từ `last`+1
    (999 → A001 = 1000, Z999 = 26973 quay về 001), nhảy qua `taken` (số của thùng
    còn hàng/vô hiệu — nhãn còn dán trên thùng). Xoay vòng tiến (không lấy lại số
    nhỏ nhất vừa trống) để số của thùng vừa hết hàng lâu bị tái dùng nhất — đỡ
    nhầm ngoài kho. Hết số → ValueError. Pure."""
    out: list[int] = []
    t = {n for n in taken if 1 <= n <= CALL_MAX}
    n = last if 1 <= last <= CALL_MAX else 0
    for _ in range(count):
        for _ in range(CALL_MAX):
            n = n + 1 if n < CALL_MAX else 1
            if n not in t:
                break
        else:
            raise ValueError(
                "Kho đã dùng hết 26.973 số thùng đang hoạt động (001–999 + A001–Z999)"
            )
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
