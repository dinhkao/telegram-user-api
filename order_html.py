"""order_html.py — Generate main order message HTML, matching Node.js buildMessageContent()."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta


def _esc(s: str) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_money(n: int) -> str:
    n = int(n or 0)
    return f"{n:,}đ"


def _to_k(n: int) -> str:
    n = int(n or 0)
    sign = "-" if n < 0 else ""
    val = round(abs(n) / 1000)
    return f"{sign}{val:,}k"


def build_order_main_message_html(order: dict, thread_id: int) -> str:
    """Generate the main order message HTML from order dict + SQLite context.

    Matches the format produced by Node.js DonHang.buildMessageContent().
    """
    # ── Status icons ───────────────────────────────────────────────
    task_status = order.get("task_status") or {}
    icons = []
    for tt in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"):
        st = task_status.get(tt) or {}
        if tt == "nhan_tien" and st.get("done") and str(st.get("note", "")).lower() == "gtr":
            icons.append("📄")
        elif tt == "nop_tien" and not st.get("done") and str(st.get("note", "")).lower() == "chieu_lay_tien":
            icons.append("🟨")
        elif st.get("done"):
            icons.append("🔘" if st.get("skip") else "✅")
        else:
            icons.append("❌")
    status_icons = "".join(icons)

    # ── Customer ────────────────────────────────────────────────────
    kh_id = order.get("khach_hang_id") or order.get("khID")
    customer_name = order.get("customer_name") or ""
    customer_line = ""
    if customer_name:
        customer_line = f"👤 <b>{_esc(customer_name)}</b> #KH{kh_id} #don_hang"

    # ── Invoice details ─────────────────────────────────────────────
    invoice = order.get("invoice") or []
    invoice_total = 0
    invoice_lines: list[str] = []
    for item in invoice:
        sp = item.get("sp", "")
        sl = int(item.get("sl", 0))
        price = int(item.get("price", 0))
        total = sl * price
        invoice_total += total
        inv_line = sp
        if sl:
            inv_line += f"\n{'SL:':5}{str(sl):>10}"
        if price:
            inv_line += f"\n{'Giá:':5}{_fmt_money(price):>10}"
        if total:
            inv_line += f"\n{'Tổng:':5}{_fmt_money(total):>10}"
        invoice_lines.append(inv_line)

    # ── Financial summary ───────────────────────────────────────────
    discount = int(order.get("discount", 0))
    pvc = int(order.get("pvc", 0))
    vat = int(order.get("vat", 0))
    current_debt = int(order.get("khDebt", 0))
    order_total_val = invoice_total + pvc + vat - discount
    final_total = order_total_val + current_debt

    payments = order.get("payments") or []
    total_payments = sum(int(p.get("amount", 0)) for p in payments if isinstance(p, dict))

    # ── Money summary line ──────────────────────────────────────────
    money_line = f"💵 <i>Hàng</i> {_to_k(invoice_total)} | <i>Nợ</i> {_to_k(current_debt)} | <i>Tổng</i> {_to_k(final_total)}"

    # ── Date ────────────────────────────────────────────────────────
    created = order.get("created", "")
    date_line = ""
    if created:
        try:
            if isinstance(created, str):
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            elif created > 1e10:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(created, tz=timezone.utc)
            vn = dt.astimezone(timezone(timedelta(hours=7)))
            date_line = f"📅 {vn.strftime('%d/%m/%Y %H:%M')}"
        except Exception:
            pass

    # ── Order text + link ───────────────────────────────────────────
    order_text = _esc(order.get("text", ""))
    order_link = f"tg://privatepost?channel=2124542200&post={thread_id}"
    main_line = f"dh {status_icons}💰 <a href=\"{order_link}\">{order_text}</a>"

    # ── Assemble expanded blockquote ────────────────────────────────
    parts: list[str] = []
    if customer_line:
        parts.append(customer_line)
        parts.append(money_line)
    if date_line:
        parts.append(date_line)
    if invoice_lines:
        parts.append("-------------------")
        parts.append("<b>Chi tiết hóa đơn:</b>")
        parts.append("<code>" + "\n\n".join(invoice_lines) + "</code>")
    if invoice_total or discount or pvc or vat or current_debt or total_payments:
        parts.append("-------------------")
        parts.append("<b>Tổng kết</b>")
        entries: list[tuple[str, str, bool]] = []
        if invoice_total:
            entries.append(("📦 Hàng:", _fmt_money(invoice_total), True))
        if discount:
            entries.append(("💰 Giảm:", f"-{_fmt_money(discount)}", True))
        if pvc:
            entries.append(("🚚 Ship:", f"+{_fmt_money(pvc)}", True))
        if vat:
            entries.append(("📊  VAT:", f"+{_fmt_money(vat)}", True))
        if order_total_val != invoice_total:
            entries.append(("🧾 Tổng đơn này:", _fmt_money(order_total_val), True))
        if current_debt:
            entries.append(("💳 Nợ trước:", _fmt_money(current_debt), True))
        entries.append(("💯 Tổng thanh toán:", _fmt_money(final_total), True))
        if total_payments:
            entries.append(("💸 Đã trả:", _fmt_money(total_payments), True))
        money_vals = [v for _, v, is_money in entries if is_money]
        max_len = max(len(v) for v in money_vals) if money_vals else 0
        for label, val, is_money in entries:
            parts.append(label)
            if is_money:
                pad = " " * (10 + max_len - len(val))
                parts.append(f"<code>{pad}{val}</code>")
            else:
                parts.append(val)

    # ── Tags line ──────────────────────────────────────────────────
    tag_parts: list[str] = ["tags:"]
    # Financial numbers (cut last 3 digits)
    fin_nums = [invoice_total, discount, pvc, vat, current_debt, final_total]
    fin_strs = []
    for n in fin_nums:
        s = str(abs(n))
        if len(s) > 3:
            s = s[:-3]
        if int(s) > 0:
            fin_strs.append(s)
    if fin_strs:
        tag_parts.append(" ".join(fin_strs))
    # Date tag
    if created:
        try:
            if isinstance(created, str):
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            elif created > 1e10:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(created, tz=timezone.utc)
            vn = dt.astimezone(timezone(timedelta(hours=7)))
            tag_parts.append(f"#tạo_{vn.day:02d}_{vn.month:02d}_{vn.year}")
        except Exception:
            pass
    tag_parts.append("#don_hang dh")
    # Debt tag if no payments
    if not total_payments:
        tag_parts.append("#nợ")
    # Pending task hashtags
    pending = []
    for tt in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"):
        st = task_status.get(tt) or {}
        if not st.get("done"):
            pending.append(f"#chua_{tt}")
    if pending:
        # Add short aliases
        alias_map = {"chua_giao_hang": "cg", "chua_soan_hang": "cs", "chua_nop_tien": "cnt"}
        for p in pending:
            base = p.replace("#", "")
            a = alias_map.get(base, "")
            tag_parts.append(p + (f" {a}" if a else ""))
    # cnhan tag: nop_tien done but nhan_tien not done
    nop_done = (task_status.get("nop_tien") or {}).get("done")
    nhan_done = (task_status.get("nhan_tien") or {}).get("done")
    if nop_done and not nhan_done:
        tag_parts.append("cnhan")
    parts.append("-------------------")
    parts.append(" ".join(tag_parts))
    return main_line + "\n<blockquote expandable>" + "\n".join(parts) + "</blockquote>"
