from __future__ import annotations
import re

from product_store.queries import get_all_products

from .search import get_customer_price_list


def parse_invoice_free_text(conn, text: str, kh_id: str | int | None = None, *, _all_products=None) -> list[dict]:
    if not text or not text.strip():
        return []
    all_products = _all_products if _all_products is not None else get_all_products(conn)
    valid_codes = {p["code"].upper() for p in all_products} if all_products else set()
    if not valid_codes:
        return []
    price_list = get_customer_price_list(conn, kh_id) if kh_id else {}
    cleaned = re.sub(r"[,\n]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(?i)(dm180)\s+(\d+)\s*l[ốo]c\b", r"\1 \2b 12", cleaned)
    tokens, invoice, i = cleaned.split(" "), [], 0
    while i < len(tokens):
        token_upper = tokens[i].upper()
        if token_upper in valid_codes:
            sp, i = token_upper, i + 1
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
                    sl1pc, explicit = 50, False
                    if i < len(tokens):
                        try:
                            sl1pc, explicit, i = int(tokens[i]), True, i + 1
                        except ValueError:
                            pass
                    if not explicit and sp.upper() == "KDXDB":
                        sl1pc = 5
                elif qc_type == "b":
                    sl1pc = 3
                    if i < len(tokens):
                        try:
                            sl1pc, i = int(tokens[i]), i + 1
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
            invoice.append({"sp": sp, "so_qc": so_qc, "qc_type": qc_type, "sl1pc": sl1pc, "sl": sl, "price": price_list.get(sp, 0), "note": None})
            continue
        i += 1
    return invoice
