from __future__ import annotations

from renderers.common import accentless_lower, fmt_money


def status_icons(task_status: dict) -> str:
    # Nộp tiền xong kiểu KÝ TOA (có/không) → bước 'nhận tiền' thành 'Gửi toa cho
    # khách': xong hiện 📄 thay ✅ (giống note 'gtr' cũ).
    _nop = task_status.get("nop_tien") or {}
    gui_toa = bool(_nop.get("done")) and str(_nop.get("note", "")).lower().split(";")[0] in ("co_ky_toa", "khong_ky_toa")
    return "".join(
        "📄" if tt == "nhan_tien" and st.get("done") and (gui_toa or str(st.get("note", "")).lower() == "gtr")
        else "🟨" if tt == "nop_tien" and not st.get("done") and str(st.get("note", "")).lower() == "chieu_lay_tien"
        else "🔘" if st.get("done") and st.get("skip")
        else "✅" if st.get("done")
        else "❌"
        for tt in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien")
        for st in [task_status.get(tt) or {}]
    )


def customer_name(order: dict, kh_id, current: str) -> str:
    if current or not kh_id:
        return current
    try:
        from order_db import _get_connection, get_customer_by_key
        conn = _get_connection()
        try:
            return (get_customer_by_key(conn, str(kh_id)) or {}).get("name") or ""
        finally:
            conn.close()
    except Exception:
        return ""


def invoice_block(invoice):
    total, lines = 0, []
    for item in invoice or []:
        sp, sl, price = item.get("sp", ""), int(item.get("sl", 0)), int(item.get("price", 0))
        total += sl * price
        line = sp
        if sl:
            line += f"\n{'SL:':5}{str(sl):>10}"
        if price:
            line += f"\n{'Giá:':5}{fmt_money(price):>10}"
        if sl * price:
            line += f"\n{'Tổng:':5}{fmt_money(sl * price):>10}"
        lines.append(line)
    return total, lines


def summary_entries(invoice_total, discount, pvc, vat, current_debt, final_total, total_payments, order_total_val, surcharges_total):
    entries = []
    if invoice_total:
        entries.append(("📦 Hàng:", fmt_money(invoice_total), True))
    if discount:
        entries.append(("💰 Giảm:", f"-{fmt_money(discount)}", True))
    if pvc:
        entries.append(("🚚 Ship:", f"+{fmt_money(pvc)}", True))
    if vat:
        entries.append(("📊  VAT:", f"+{fmt_money(vat)}", True))
    if order_total_val != invoice_total:
        entries.append(("🧾 Tổng đơn này:", fmt_money(order_total_val), True))
    if current_debt:
        entries.append(("💳 Nợ trước:", fmt_money(current_debt), True))
    entries.append(("💯 Tổng thanh toán:", fmt_money(final_total), True))
    if total_payments:
        entries.append(("💸 Đã trả:", fmt_money(total_payments), True))
    return entries


def tag_parts(order_text, invoice_total, discount, pvc, vat, current_debt, final_total, created_dt, total_payments, task_status):
    tags = ["tags:", accentless_lower(order_text)]
    fin = []
    for n in (invoice_total, discount, pvc, vat, current_debt, final_total):
        try:
            n = int(n or 0)  # ép int trước: tránh "5.0"[:-3]=="" (crash) + cắt nghìn sai với float
        except (TypeError, ValueError):
            continue
        s = str(abs(n))
        s = s[:-3] if len(s) > 3 else s
        if s and int(s) > 0:
            fin.append(s)
    if fin:
        tags.append(" ".join(fin))
    if created_dt:
        tags.append(f"#tạo_{created_dt.day:02d}_{created_dt.month:02d}_{created_dt.year}")
    tags.append("#don_hang dh")
    if not total_payments:
        tags.append("#nợ")
    pending = [f"#chua_{tt}" for tt in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien") if not (task_status.get(tt) or {}).get("done")]
    if pending:
        alias = {"chua_giao_hang": "cg", "chua_soan_hang": "cs", "chua_nop_tien": "cnt"}
        tags.extend(p + (f" {alias.get(p.replace('#', ''), '')}" if alias.get(p.replace("#", ""), "") else "") for p in pending)
    if (task_status.get("nop_tien") or {}).get("done") and not (task_status.get("nhan_tien") or {}).get("done"):
        tags.append("cnhan")
    return tags
