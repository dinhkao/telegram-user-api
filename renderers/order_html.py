from __future__ import annotations

import os
from datetime import timezone, timedelta

from renderers.common import esc, internal_group_id, to_k, vn_dt
from renderers.order_parts import customer_name, invoice_block, status_icons, summary_entries, tag_parts

_CUSTOMER_GROUP_ID = int(os.getenv("GROUP_KHACHHANG_ID", "-1002437761799"))


def build_order_main_message_html(order: dict, thread_id: int) -> str:
    task_status = order.get("task_status") or {}
    kh_id = order.get("khach_hang_id") or order.get("khID")
    customer = customer_name(order, kh_id, order.get("customer_name") or "")
    customer_line = f'👤 <b><a href="tg://privatepost?channel={internal_group_id(_CUSTOMER_GROUP_ID)}&post={kh_id}">{esc(customer)}</a></b> #KH{kh_id} #don_hang' if customer else ""
    # mã/tên SP trong tin nhắn = bản HIỆN HÀNH (re-render sau đổi mã tự cập nhật)
    from order_store.display import resolve_invoice_display
    invoice_total, invoice_lines = invoice_block(resolve_invoice_display(order.get("invoice") or []))
    discount = int(order.get("discount", 0))
    pvc = int(order.get("pvc", 0))
    vat = int(order.get("vat", 0))
    current_debt = int(order.get("khDebt", 0))
    order_total_val = invoice_total + pvc + vat - discount
    final_total = order_total_val + current_debt
    payments = order.get("payments") or []
    total_payments = sum(int(p.get("amount", 0)) for p in payments if isinstance(p, dict))
    money_line = f"💵 <i>Hàng</i> {to_k(invoice_total)} | <i>Nợ</i> {to_k(current_debt)} | <i>Tổng</i> {to_k(final_total)}"
    created_dt = vn_dt(order.get("created", ""))
    date_line = f"📅 {created_dt.astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')}" if created_dt else ""
    order_text = esc(order.get("text", ""))
    order_link = f"tg://privatepost?channel=2124542200&post={thread_id}"
    order_start_key = order.get("firebase_key") or thread_id
    bot_start_url = f"tg://resolve?domain=letrangdonhangbot&start={order_start_key}"
    main_line = f'dh <a href="{bot_start_url}">{status_icons(task_status, order.get("stock_confirmed"))}{"💰" if (task_status.get("nhan_tien") or {}).get("done") else "😠"}</a> <a href="{order_link}">{order_text}</a>'
    parts = []
    if customer_line: parts.extend([customer_line, money_line])
    if date_line: parts.append(date_line)
    if invoice_lines: parts.extend(["-------------------", "<b>Chi tiết hóa đơn:</b>", "<code>" + "\n\n".join(invoice_lines) + "</code>"])
    if invoice_total or discount or pvc or vat or current_debt or total_payments:
        entries = summary_entries(invoice_total, discount, pvc, vat, current_debt, final_total, total_payments, order_total_val, 0)
        max_len = max((len(v) for _, v, is_money in entries if is_money), default=0)
        parts.extend(["-------------------", "<b>Tổng kết</b>"])
        for label, val, is_money in entries:
            parts.append(label)
            parts.append(f"<code>{' ' * (10 + max_len - len(val))}{val}</code>" if is_money else val)
    parts.extend(["-------------------", " ".join(tag_parts(order.get("text", ""), invoice_total, discount, pvc, vat, current_debt, final_total, created_dt, total_payments, task_status))])
    updated_dt = vn_dt(order.get("updated_at", ""))
    updated_line = f"<i>Lần cuối cập nhật: {updated_dt.astimezone(timezone(timedelta(hours=7))).strftime('%H:%M %d/%m/%Y')}</i>" if updated_dt else ""
    result = main_line + (f"\n{updated_line}" if updated_line else "") + "\n<blockquote expandable>" + "\n".join(parts) + "</blockquote>"
    return f"🗑️ <b><i>ĐƠN HÀNG ĐÃ XÓA</i></b>\n\n{result}" if order.get("del") else result
