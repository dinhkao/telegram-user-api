from __future__ import annotations


def _fmt_invoice_html(invoice: dict) -> str:
    lines = ["<b>🧾 Hóa đơn</b>", ""]
    code = invoice.get("code", "N/A")
    created = invoice.get("createdDate", "")[:10] if invoice.get("createdDate") else ""
    lines.append(f"Mã HĐ: <b>{code}</b>  |  {created}")
    lines.append(f"Tổng: <b>{invoice.get('total', 0):,}đ</b>")
    lines.append("")
    details = invoice.get("invoiceDetails", [])
    if details:
        for item in details:
            name = item.get("productName", "?")
            qty = item.get("quantity", 0)
            price = item.get("price", 0)
            sub = item.get("subTotal", 0)
            lines.append(f"• {name} x{qty} — {int(price):,}đ = {int(sub):,}đ")
    lines.append("")
    if invoice.get("totalPayment"):
        lines.append(f"Đã thanh toán: {invoice.get('totalPayment', 0):,}đ")
    lines.append(f"Còn lại: {invoice.get('total', 0) - invoice.get('totalPayment', 0):,}đ")
    return "\n".join(lines)


def _fmt_receipt(order: dict, invoices: list[dict] | None = None) -> str:
    lines = []
    lines.append("═" * 32)
    lines.append("         PHIẾU THU TIỀN")
    lines.append("═" * 32)
    customer = order.get("khach_hang") or order.get("name") or "N/A"
    phone = order.get("so_dien_thoai") or order.get("phone") or "N/A"
    lines.append(f"Khách hàng: {customer}")
    lines.append(f"Điện thoại: {phone}")
    lines.append(f"Mã ĐH:     {order.get('thread_id', 'N/A')}")
    lines.append("─" * 32)
    if invoices:
        for inv in invoices:
            for item in inv.get("invoiceDetails", []):
                name = (item.get("productName") or "?")[:22]
                qty = item.get("quantity", 0)
                price = item.get("price", 0)
                sub = item.get("subTotal", 0)
                lines.append(f"{name:<22s} {qty:>4d}")
                lines.append(f"  {int(price):>10,}đ × {qty:>4d} = {int(sub):>12,}đ")
    else:
        for item in order.get("items") or order.get("san_pham") or []:
            name = (item.get("name") or item.get("ten") or "?")[:22]
            qty = item.get("quantity") or item.get("sl") or 0
            price = item.get("price") or item.get("gia") or 0
            sub = int(qty) * int(price)
            lines.append(f"{name:<22s} {qty:>4d}")
            lines.append(f"  {int(price):>10,}đ × {qty:>4d} = {sub:>12,}đ")
    lines.append("─" * 32)
    total = order.get("tong_cong") or order.get("total") or 0
    payments = order.get("payments", [])
    paid = sum(p.get("amount", 0) for p in payments)
    lines.append(f"TỔNG CỘNG: {int(total):>21,}đ")
    if paid:
        lines.append(f"ĐÃ TRẢ:    {int(paid):>21,}đ")
        lines.append(f"CÒN LẠI:   {int(total - paid):>21,}đ")
    lines.append("═" * 32)
    lines.append("Cảm ơn quý khách!")
    return "\n".join(lines)


def _fmt_payment_list(payments: list[dict]) -> str:
    lines = ["<b>💰 Thanh toán:</b>", ""]
    total = 0
    for p in payments:
        amount = p.get("amount", 0)
        method = p.get("method", "?")
        pid = p.get("id", "")[:12]
        created = p.get("created_at", "")[:10]
        lines.append(f"• <b>{amount:,}đ</b> — {method} ({pid}) {created}")
        total += amount
    lines.append(f"<b>Tổng đã trả: {total:,}đ</b>")
    return "\n".join(lines)


def _fmt_debt_list(debts: list[dict]) -> str:
    grand_total = sum(d["total"] for d in debts)
    grand_remaining = sum(d["remaining"] for d in debts)
    lines = [
        "<b>📊 Tất cả công nợ:</b>",
        f"Tổng nợ: <b>{grand_remaining:,}đ</b> / {grand_total:,}đ",
        "",
    ]
    for d in sorted(debts, key=lambda x: x["remaining"], reverse=True):
        lines.append(f"• {d['customer']} — còn <b>{d['remaining']:,}đ</b>")
    return "\n".join(lines)


def _fmt_analysis(product_counts: list[tuple[str, int]]) -> str:
    lines = ["<b>📊 Top sản phẩm (200 đơn gần nhất):</b>", ""]
    for i, (name, count) in enumerate(product_counts, 1):
        lines.append(f"{i}. <b>{name}</b> — {count} lần")
    return "\n".join(lines)
