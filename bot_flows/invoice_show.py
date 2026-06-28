"""bot_don_hang/flows/invoice_show.py — Render invoice HTML from cached session."""
from telethon import Button

from bot_core import config, keyboards
from bot_core.store import reset_timer


async def handle_show_invoice(bot, event, s):
    """Build invoice HTML from cached session — zero DB/API calls."""
    invoice = s.invoice or []
    kb = keyboards.build_inline_invoice_keyboard(
        has_items=bool(invoice),
        has_kv=bool(s.kv_invoice_id),
    )

    invoice_html = ""
    if invoice:
        lines = []
        for item in invoice:
            if not isinstance(item, dict):
                continue
            code = item.get("sp") or ""
            qty = item.get("sl") or 0
            price = item.get("price") or 0
            total = qty * price
            parts = [code]
            if qty > 0:
                parts.append(f"SL:{qty:>10}")
            if price > 0:
                parts.append(f"Giá:{price:>9,}")
            if total > 0:
                parts.append(f"Tổng:{total:>8,}")
            lines.append("\n".join(parts))
        invoice_html = f"<b>Chi tiết hóa đơn:</b>\n<code>{'\n\n'.join(lines)}</code>"

    summary_html = ""
    if invoice or s.discount or s.pvc or s.vat or s.kh_debt or s.payments:
        summary_html = _build_summary_html(s)

    parts = []
    if invoice_html:
        parts.append("-------------------")
        parts.append(invoice_html)
    if not invoice_html and summary_html:
        parts.append("Đơn hàng chưa được nhập sản phẩm")
    if summary_html:
        parts.append("-------------------")
        parts.append("<b>Tổng kết</b>")
        parts.append(summary_html)
    html = "\n".join(parts) if parts else f"Hoá đơn trống cho đơn {s.order_id}."

    await event.reply(html, parse_mode="html", buttons=kb)
    reset_timer(s.chat_id)


def _build_summary_html(s) -> str:
    invoice_total = sum(
        (it.get("price") or 0) * (it.get("sl") or 0)
        for it in s.invoice or []
        if isinstance(it, dict)
    )
    discount, pvc, vat, kh_debt = s.discount, s.pvc, s.vat, s.kh_debt
    payments = s.payments or []
    total_payments = sum(p.get("amount", 0) for p in payments if isinstance(p, dict))

    order_total = invoice_total + pvc + vat - discount
    final_total = order_total + kh_debt

    if not (invoice_total or discount or pvc or vat or kh_debt != 0 or total_payments):
        return ""

    entries = []
    fmt = lambda n: f"{n:,.0f}đ"

    if invoice_total > 0 and final_total != invoice_total:
        entries.append(("📦 Hàng:", fmt(invoice_total), True))
    if discount > 0:
        entries.append(("💰 Giảm:", f"-{fmt(discount)}", True))
    if pvc > 0:
        entries.append(("🚚 Ship:", f"+{fmt(pvc)}", True))
    if vat > 0:
        entries.append(("📊  VAT:", f"+{fmt(vat)}", True))
    if (invoice_total or discount or pvc or vat) and order_total != invoice_total:
        entries.append(("🧾 Tổng đơn này:", fmt(order_total), True))
    if kh_debt != 0:
        entries.append(("💳 Nợ trước:", fmt(kh_debt), True))
    entries.append(("💯 Tổng thanh toán:", fmt(final_total), True))

    if total_payments > 0:
        entries.append(("💸 Đã trả:", fmt(total_payments), True))
    elif s.task_status:
        entries.extend(_build_payment_status_entries(s.task_status))

    money_values = [v for _, v, is_money in entries if is_money]
    max_money_len = max((len(v) for v in money_values), default=0)
    base_indent = 10
    lines = []
    for label, value, is_money in entries:
        lines.append(label)
        if is_money:
            extra_pad = max(0, max_money_len - len(value))
            pad = " " * (base_indent + extra_pad)
            lines.append(f"<code>{pad}{value}</code>")
        else:
            lines.append(value)
    return "\n".join(lines)


def _build_payment_status_entries(task_status: dict) -> list[tuple[str, str, bool]]:
    entries = []
    nop = task_status.get("nop_tien") or {}
    if nop.get("done"):
        nhan = task_status.get("nhan_tien") or {}
        mode = nhan.get("nhanTienMode") or "nhan_tien"
        done = nhan.get("done")
        icon = "✅" if done else "❌"
        if mode == "gui_toa":
            text = "Đã gửi toa" if done else "Chưa gửi toa"
            entries.append(("📄 Toa:", f"{icon} {text}", False))
        elif mode == "kiem_tra_ck":
            text = "Đã kiểm tra CK" if done else "Chưa kiểm tra CK"
            entries.append(("🏦 CK:", f"{icon} {text}", False))
        else:
            text = "Đã nhận tiền" if done else "Chưa nhận tiền"
            entries.append(("💵 Nhận:", f"{icon} {text}", False))
    else:
        entries.append(("💸 Trả:", "❌ Chưa nộp tiền", False))
    return entries
