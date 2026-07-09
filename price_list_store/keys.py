"""Key bảng giá ↔ danh tính SP. Key CHUẨN = str(products.id) (toàn chữ số, bất
biến khi đổi mã); key mã TEXT = legacy (SP không có trong danh mục — giữ nguyên,
không xoá dấu vết). Mã SP không bao giờ toàn chữ số (validate ở create/rename)
nên phân biệt được bằng isdigit. Dùng cho CẢ bảng giá chung (bang_gia_moi) lẫn
bảng giá riêng từng khách (customers.$.personal_price_list).
Nối: product_store (resolve/get_product_by_id/code_alias_map)."""
from __future__ import annotations

from product_store import code_alias_map, get_product_by_id, resolve_code


def is_pid_key(k) -> bool:
    return str(k).isdigit()


def to_pid_key(conn, sp) -> str:
    """Mã (hiện hành/cũ) → '<pid>'. Không resolve được → mã UPPER (legacy key)."""
    s = str(sp or "").strip()
    if not s:
        return ""
    if s.isdigit():  # đã là pid key
        return s
    prod = resolve_code(conn, s)
    return str(prod["id"]) if prod else s.upper()


def effective_code_prices(conn, raw: dict | None, *, aliases: bool = True) -> dict[str, int]:
    """{key: giá} (pid/legacy trộn lẫn) → {MÃ HIỆN HÀNH: giá} để parser/hiển thị.

    - key pid → mã hiện hành của SP (SP đã xoá → bỏ, giá chết không hiện).
    - key mã legacy → giữ nguyên (UPPER).
    - aliases=True: thêm MÃ CŨ của các SP có giá (gõ mã cũ vẫn ăn giá), không đè
      key đã có (mã tái dùng → SP hiện tại thắng)."""
    out: dict[str, int] = {}
    pid_prices: dict[int, int] = {}
    for k, v in (raw or {}).items():
        try:
            price = int(v)
        except (TypeError, ValueError):
            continue
        if is_pid_key(k):
            prod = get_product_by_id(conn, int(k))
            if prod:
                out[prod["code"].upper()] = price
                pid_prices[int(k)] = price
        else:
            out[str(k).strip().upper()] = price
    if aliases and pid_prices:
        for old_code, pid in code_alias_map(conn).items():
            if pid in pid_prices and old_code not in out:
                out[old_code] = pid_prices[pid]
    return out


def migrate_price_keys(conn, raw: dict | None) -> dict:
    """Đổi key mã → key pid (1 lần, cho migration). Mã không trong danh mục giữ
    nguyên (legacy). Giá trị giữ nguyên."""
    out: dict = {}
    for k, v in (raw or {}).items():
        out[to_pid_key(conn, k)] = v
    return out
