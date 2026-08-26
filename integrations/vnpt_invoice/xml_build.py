"""Dựng xmlInvData (TT78) cho hoá đơn nháp VNPT + tính tổng tiền.

Thuần, không IO — unit-tested. Giá nhập là giá CHƯA gồm VAT (Duy chốt
2026-08-26); 1 mức thuế suất chung cho cả hoá đơn (-1 = không chịu thuế).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .amount_words import amount_to_words

# Mức thuế hợp lệ: -1 = KCT (không chịu thuế), còn lại là %
VAT_RATES = (-1, 0, 5, 8, 10)


def _fmt_qty(q: float) -> str:
    """3.0 → '3', 3.5 → '3.5' (SL hoá đơn có thể lẻ — xem utils/qty.py)."""
    f = float(q)
    return str(int(f)) if f == int(f) else f"{f:g}"


def compute_totals(lines: list[dict], vat_rate: int) -> dict:
    """lines = [{name, unit, qty, price}] → {lines[+amount], total, vat_amount, amount}."""
    out_lines = []
    total = 0
    for ln in lines:
        amount = int(round(float(ln["qty"]) * float(ln["price"])))
        total += amount
        out_lines.append({**ln, "amount": amount})
    vat_amount = 0 if vat_rate < 0 else int(round(total * vat_rate / 100))
    return {
        "lines": out_lines,
        "total": total,
        "vat_amount": vat_amount,
        "amount": total + vat_amount,
    }


def build_invoice_xml(
    *,
    fkey: str,
    buyer: dict,
    lines: list[dict],
    vat_rate: int,
) -> str:
    """Dựng chuỗi <Invoices>…</Invoices> cho ImportInvByPattern/updateInvoice.

    buyer: {cus_name, buyer_name, tax_code, address, phone, email, cus_code,
    payment_method} — thiếu key nào thì thành chuỗi rỗng.
    """
    if vat_rate not in VAT_RATES:
        raise ValueError(f"thuế suất không hợp lệ: {vat_rate}")
    if not lines:
        raise ValueError("hoá đơn không có dòng hàng nào")
    t = compute_totals(lines, vat_rate)

    def e(key: str) -> str:
        return escape(str(buyer.get(key) or "").strip())

    prods = []
    for ln in t["lines"]:
        name = str(ln.get("name") or "").strip()
        if not name:
            raise ValueError("dòng hàng thiếu tên")
        prods.append(
            "<Product>"
            f"<Code>{escape(str(ln.get('code') or ''))}</Code>"
            f"<ProdName>{escape(name)}</ProdName>"
            f"<ProdUnit>{escape(str(ln.get('unit') or '').strip())}</ProdUnit>"
            f"<ProdQuantity>{_fmt_qty(ln['qty'])}</ProdQuantity>"
            f"<ProdPrice>{int(ln['price'])}</ProdPrice>"
            # <Total> = cột THÀNH TIỀN trên mẫu in (thiếu là cột trống — thực nghiệm);
            # <Amount> giữ kèm cùng giá trị (chưa thuế, 1 mức thuế chung cả HĐ)
            f"<Total>{ln['amount']}</Total>"
            f"<Amount>{ln['amount']}</Amount>"
            "</Product>"
        )
    invoice = (
        "<Invoice>"
        # <CusCode> BẮT BUỘC có mặt theo XSD (thiếu = ERR:3 "incomplete content")
        # nhưng luôn để TRỐNG — Duy bỏ mã khách hàng 2026-08-26.
        # <Email> bị XSD từ chối; email NHẬN hoá đơn đúng thẻ là <EmailDeliver>.
        "<CusCode></CusCode>"
        f"<Buyer>{e('buyer_name')}</Buyer>"
        f"<CusName>{e('cus_name')}</CusName>"
        f"<CusAddress>{e('address')}</CusAddress>"
        f"<CusPhone>{e('phone')}</CusPhone>"
        f"<CusTaxCode>{e('tax_code')}</CusTaxCode>"
        f"<EmailDeliver>{e('email')}</EmailDeliver>"
        f"<PaymentMethod>{e('payment_method') or 'TM/CK'}</PaymentMethod>"
        f"<Products>{''.join(prods)}</Products>"
        f"<Total>{t['total']}</Total>"
        "<DiscountAmount>0</DiscountAmount>"
        f"<VATRate>{vat_rate}</VATRate>"
        f"<VATAmount>{t['vat_amount']}</VATAmount>"
        f"<Amount>{t['amount']}</Amount>"
        f"<AmountInWords>{escape(amount_to_words(t['amount']))}</AmountInWords>"
        "<CurrencyUnit>VND</CurrencyUnit>"
        "<ExchangeRate>1.0</ExchangeRate>"
        "</Invoice>"
    )
    return f"<Invoices><Inv><key>{escape(fkey)}</key>{invoice}</Inv></Invoices>"
