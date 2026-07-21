from __future__ import annotations
import re

from product_store.queries import get_all_products

from .search import get_customer_price_list
from .quy_cach import load_quy_cach, thung_qty, bich_qty

# Quy cách đóng gói (số cái / 1 thùng, 1 bịch, lốc DM180) giờ ở order_store.quy_cach,
# admin sửa được từ webapp (#/quy-cach). Nhập tay số sau <n>t / <n>b vẫn ghi đè.


def parse_invoice_free_text(conn, text: str, kh_id: str | int | None = None, *, _all_products=None) -> list[dict]:
    if not text or not text.strip():
        return []
    all_products = _all_products if _all_products is not None else get_all_products(conn)
    valid_codes = {p["code"].upper() for p in all_products} if all_products else set()
    if not valid_codes:
        return []
    # MÃ CŨ (đã đổi) vẫn nhận: map mã_cũ → mã hiện hành, item lưu mã hiện hành
    from product_store import code_alias_map
    by_id = {p["id"]: p["code"].upper() for p in all_products if p.get("id") is not None}
    alias_codes = {}
    try:
        alias_codes = {old: by_id[pid] for old, pid in code_alias_map(conn).items() if pid in by_id}
    except Exception:  # noqa: BLE001 — thiếu bảng history (DB test cũ) thì bỏ qua
        pass
    valid_codes |= set(alias_codes)
    price_list = get_customer_price_list(conn, kh_id) if kh_id else {}
    cfg = load_quy_cach(conn)
    cleaned = re.sub(r"[,\n]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(?i)(dm180)\s+(\d+)\s*l[ốo]c\b", rf"\1 \2b {cfg['dm180_loc']}", cleaned)
    tokens, invoice, i = cleaned.split(" "), [], 0
    while i < len(tokens):
        token_upper = tokens[i].upper()
        if token_upper in valid_codes:
            # mã cũ → chuẩn hoá về mã hiện hành ngay lúc parse
            sp, i = alias_codes.get(token_upper, token_upper), i + 1
            if i >= len(tokens):
                i += 1
                continue
            next_token, qc_type, so_qc, sl1pc, has_qc = tokens[i], None, [1], 0, False
            m_t, m_b, m_tb = re.match(r"^(\d+)t$", next_token), re.match(r"^(\d+)b$", next_token), re.match(r"^([\d.]+)t([\d.]+)b$", next_token)
            if m_t:
                qc_type, so_qc, has_qc, i = "t", [int(m_t.group(1))], True, i + 1
            elif m_b:
                qc_type, so_qc, has_qc, i = "b", [int(m_b.group(1))], True, i + 1
            elif m_tb:
                qc_type, so_qc, has_qc, i = "tb", [float(m_tb.group(1)), float(m_tb.group(2))], True, i + 1
            if has_qc:
                if qc_type in ("t", "tb"):
                    sl1pc = thung_qty(sp, cfg)
                    if i < len(tokens):
                        try:
                            sl1pc, i = int(tokens[i]), i + 1  # số/thùng nhập tay → ghi đè
                        except ValueError:
                            pass
                elif qc_type == "b":
                    sl1pc = bich_qty(sp, cfg)
                    if i < len(tokens):
                        try:
                            sl1pc, i = int(tokens[i]), i + 1  # số/bịch nhập tay → ghi đè
                        except ValueError:
                            pass
            else:
                try:
                    sl1pc, i = int(next_token), i + 1
                except ValueError:
                    continue
            sl = int(sl1pc)
            for v in so_qc:
                sl *= v
            # Giá: mặc định theo bảng giá khách; nếu token kế tiếp là SỐ (và không
            # phải mã SP) → dùng làm GIÁ BÁN ghi đè (user tự nhập giá sau số lượng).
            price = price_list.get(sp, 0)
            if i < len(tokens) and tokens[i].upper() not in valid_codes:
                try:
                    price = int(tokens[i])
                    i += 1
                except ValueError:
                    pass
            invoice.append({"sp": sp, "so_qc": so_qc, "qc_type": qc_type, "sl1pc": sl1pc, "sl": sl, "price": price, "note": None})
            continue
        i += 1
    return invoice
