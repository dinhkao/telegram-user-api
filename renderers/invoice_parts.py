from __future__ import annotations


def format_currency(amount) -> str:
    try:
        return f"{int(amount):,}"
    except (TypeError, ValueError):
        return str(amount)


def parse_number(v):
    if isinstance(v, (int, float)):
        return int(v)
    if not v:
        return 0
    import re
    return int(re.sub(r"[^\d]", "", str(v))) or 0


def get_surcharges(invoice: dict, hints: dict | None = None) -> list[dict]:
    hints = hints or {}
    surcharges = []
    for s in invoice.get("invoiceOrderSurcharges", []) or []:
        if not isinstance(s, dict):
            continue
        price = s.get("price") or s.get("amount") or 0
        if price <= 0:
            continue
        raw_name = (s.get("name") or "").strip().lower()
        code = str(s.get("code") or "")
        code_lc = code.lower()
        s_id = s.get("id")
        is_shipping = s_id == 1000000298 or code == "THK000003"
        is_vat = s_id == 1865 or code == "THK000001"
        looks_like_vat = "vat" in code_lc or "tax" in code_lc or "vat" in raw_name
        looks_like_ship = any(k in code_lc for k in ["ship", "transport", "delivery"]) or "vận chuyển" in raw_name or "van chuyen" in raw_name
        generic_names = {"phí khác", "phi khac", "khác", "khac", "lệ phí khác", "le phi khac"}
        is_generic = raw_name in generic_names
        if is_shipping or looks_like_ship:
            name = "Phí vận chuyển"
        elif is_vat or looks_like_vat:
            name = "VAT"
        elif (s.get("name") or "").strip() and not is_generic:
            name = s["name"].strip()
        else:
            name = "Phí khác"
        surcharges.append({"name": name, "amount": price})
    try:
        expected_vat = int(hints.get("expectedVAT", 0))
        expected_pvc = int(hints.get("expectedPVC", 0))
        has_label = lambda label: any(s["name"] == label for s in surcharges)
        for s in surcharges:
            if s["name"] == "Phí khác":
                if not has_label("VAT") and expected_vat > 0 and abs(s["amount"] - expected_vat) < 1:
                    s["name"] = "VAT"
                elif not has_label("Phí vận chuyển") and expected_pvc > 0 and abs(s["amount"] - expected_pvc) < 1:
                    s["name"] = "Phí vận chuyển"
    except Exception:
        pass
    return surcharges


def build_product_rows(details):
    rows = []
    total = 0
    for i, item in enumerate(details):
        name = item.get("productName") or item.get("productCode", "?")
        qty = item.get("quantity", 0)
        price = item.get("price", 0)
        sub = item.get("subTotal") or (price * qty)
        total += sub
        rows.append(f"""<tr>
        <td class="stt">{i + 1}</td>
        <td>{name}</td>
        <td class="so-luong">{qty}</td>
        <td class="so-luong">{format_currency(price)}</td>
        <td class="thanh-tien">{format_currency(sub)}</td>
      </tr>""")
    return "".join(rows), total


def build_summary_rows(tong_tien_hang, surcharges, discount, debt):
    total_surcharges = sum(s["amount"] for s in surcharges)
    tong_don_nay = tong_tien_hang + total_surcharges - discount
    tong_thanh_toan = tong_don_nay + debt
    rows = [f"""<tr><td class="strict-width"></td><td class="to-bold">Tổng tiền hàng</td><td class="money-column">{format_currency(tong_tien_hang)}</td></tr>"""]
    rows.extend(f"""<tr><td></td><td class="to-bold">{s['name']}</td><td class="money-column">{format_currency(s['amount'])}</td></tr>""" for s in surcharges)
    if discount > 0:
        rows.append(f"""<tr><td></td><td class="to-bold">Giảm giá</td><td class="money-column">-{format_currency(discount)}</td></tr>""")
    if debt != 0 and (total_surcharges > 0 or discount > 0):
        rows.append(f"""<tr><td></td><td class="to-bold">Tổng đơn này</td><td class="money-column">{format_currency(tong_don_nay)}</td></tr>""")
    if debt != 0:
        rows.append(f"""<tr><td></td><td class="to-bold">Nợ trước</td><td class="money-column">{'-' if debt < 0 else ''}{format_currency(abs(debt))}</td></tr>""")
    rows.append(f"""<tr><td></td><td class="to-bold">Tổng thanh toán</td><td class="money-column">{format_currency(tong_thanh_toan)}</td></tr>""")
    return "".join(rows), total_surcharges, tong_don_nay, tong_thanh_toan
