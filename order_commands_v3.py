"""order_commands_v3.py — Phase 3: KiotViet invoice, print, payment, debt, analysis handlers."""
from __future__ import annotations
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, UTC

from telethon import events
from telethon.tl.types import MessageService

from order_db import (
    _get_connection,
    get_order_by_thread_id,
    get_customer_kv_id,
    search_products,
    _call_final_telegram,
)
from kiotviet import (
    search_products_kv,
    create_invoice as kv_create_invoice,
    get_invoices_by_order,
    get_invoice_detail,
    get_payment_methods,
    process_payment,
    delete_payment_kv,
    create_payment_kv,
    get_customer_debt_kv,
)
from payment_db import (
    get_payments,
    add_payment,
    delete_payment_record,
    calculate_debt,
    get_all_debts,
)

log = logging.getLogger("order_commands_v3")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")


def _extract_thread_id(msg) -> int | None:
    thread_id = None
    if msg.reply_to:
        thread_id = (
            getattr(msg.reply_to, "reply_to_top_id", None)
            or getattr(msg.reply_to, "reply_to_msg_id", None)
        )
        if thread_id and not getattr(msg.reply_to, "forum_topic", False):
            thread_id = getattr(msg.reply_to, "reply_to_top_id", None)
    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None)
    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw:
            r = getattr(raw, "reply_to", None)
            if r:
                thread_id = getattr(r, "reply_to_top_id", None)
    return thread_id


def _call_final(endpoint: str, body: dict, timeout: int = 10) -> dict | None:
    return _call_final_telegram(endpoint, body, timeout)


# ── Formatting ──────────────────────────────────────────────────────

def _fmt_invoice_html(invoice: dict) -> str:
    """Format a KiotViet invoice as HTML."""
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
    """Generate Vietnamese receipt text."""
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

    # Products from invoices
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
        # Products from order
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
    """Format payment list as HTML."""
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
    """Format debt list as HTML."""
    grand_total = sum(d["total"] for d in debts)
    grand_remaining = sum(d["remaining"] for d in debts)
    lines = [
        "<b>📊 Tất cả công nợ:</b>",
        f"Tổng nợ: <b>{grand_remaining:,}đ</b> / {grand_total:,}đ",
        "",
    ]
    for d in sorted(debts, key=lambda x: x["remaining"], reverse=True):
        lines.append(
            f"• {d['customer']} — còn <b>{d['remaining']:,}đ</b>"
        )
    return "\n".join(lines)


def _fmt_analysis(product_counts: list[tuple[str, int]]) -> str:
    """Format product analysis as HTML."""
    lines = ["<b>📊 Top sản phẩm (200 đơn gần nhất):</b>", ""]
    for i, (name, count) in enumerate(product_counts, 1):
        lines.append(f"{i}. <b>{name}</b> — {count} lần")
    return "\n".join(lines)


# ── Handler registration ────────────────────────────────────────────

def register_order_commands_v3(client):
    """Register Phase 3 handlers: invoice, print, payment, debt, analysis."""
    db_conn = _get_connection()
    log.info("order_commands_v3 listening on chat %d", ORDER_GROUP_ID)

    # ── SHOW INVOICE ────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_show_invoice(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "show invoice": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        try:
            invoices = get_invoices_by_order(str(thread_id))
            if not invoices:
                await client.send_message(msg.chat_id, "❌ Chưa có hóa đơn", reply_to=msg.id)
                return
            html = _fmt_invoice_html(invoices[0])
            await client.send_message(msg.chat_id, html, reply_to=msg.id, parse_mode="html")
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi KiotViet: {e}", reply_to=msg.id)

    # ── PRINT ───────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_print(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "print": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        result = _call_final("/api/order/handle-print", {
            "thread_id": thread_id,
            "user_id": getattr(msg, "sender_id", None),
        })
        reply = result.get("reply", "✅ Đã in phiếu") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    # ── PAYMENT: ck / tm ────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_ck(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^ck\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        method_code = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        total = order.get("tong_cong") or order.get("total") or 0
        user_id = getattr(msg, "sender_id", None)
        # 1. Create KiotViet payment
        try:
            customer_id = order.get("kiotviet_customer_id") or order.get("khID")
            payment_result = create_payment_kv(total, method_code, customer_id=customer_id, order_code=str(thread_id))
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi KiotViet: {e}", reply_to=msg.id)
            return
        # 2. Save to SQLite
        payment = {"amount": total, "method": method_code, "type": "transfer", "kiotviet_id": payment_result.get("id")}
        ok, message = add_payment(db_conn, thread_id, payment)
        # 3. Bridge to Node.js for Firebase + notifications
        _call_final("/api/order/after-payment", {"thread_id": thread_id, "amount": total, "method": method_code, "user_id": user_id})
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_tm(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^tm\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        method_code = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        total = order.get("tong_cong") or order.get("total") or 0
        user_id = getattr(msg, "sender_id", None)
        # 1. Create KiotViet payment
        try:
            customer_id = order.get("kiotviet_customer_id") or order.get("khID")
            payment_result = create_payment_kv(total, method_code, customer_id=customer_id, order_code=str(thread_id))
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi KiotViet: {e}", reply_to=msg.id)
            return
        # 2. Save to SQLite
        payment = {"amount": total, "method": method_code, "type": "cash", "kiotviet_id": payment_result.get("id")}
        ok, message = add_payment(db_conn, thread_id, payment)
        # 3. Bridge to Node.js for Firebase + notifications
        _call_final("/api/order/after-payment", {"thread_id": thread_id, "amount": total, "method": method_code, "user_id": user_id})
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── /payments, /del_payment_<id>, /orders ────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_payments(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/payments": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        payments = get_payments(db_conn, thread_id)
        if not payments:
            await client.send_message(msg.chat_id, "❌ Chưa có thanh toán nào", reply_to=msg.id)
            return
        await client.send_message(msg.chat_id, _fmt_payment_list(payments), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_del_payment(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^/del_payment_(.+)$", (msg.text or "").strip())
        if not m: return
        payment_id = m.group(1)
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        ok, message = delete_payment_record(db_conn, thread_id, payment_id)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_orders(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/orders": return
        # List recent orders (last 20)
        cur = db_conn.execute(
            """SELECT thread_id, json FROM orders WHERE deleted_at IS NULL
               AND json IS NOT NULL ORDER BY updated_at DESC LIMIT 20"""
        )
        lines = ["<b>📋 Đơn hàng gần đây:</b>", ""]
        for row in cur:
            order = json.loads(row["json"])
            name = order.get("khach_hang", order.get("name", "N/A"))
            total = order.get("tong_cong") or order.get("total") or 0
            status = order.get("trang_thai", "")
            lines.append(f"• {name} — <b>{int(total):,}đ</b> ({status})")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── DEBT ────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_debt(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/debt": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        kh_id = order.get("khach_hang_id") or order.get("khID")
        if not kh_id:
            await client.send_message(msg.chat_id, "❌ Đơn hàng này chưa được gán khách hàng.", reply_to=msg.id)
            return
        customer_id = get_customer_kv_id(db_conn, str(kh_id))
        if not customer_id:
            await client.send_message(msg.chat_id, "❌ Khách hàng này không có mã KiotViet.", reply_to=msg.id)
            return
        try:
            debt = get_customer_debt_kv(customer_id)
            lines = [
                "<b>📊 Công nợ (KiotViet):</b>",
                f"Khách: <b>{debt.get('name', 'N/A')}</b>",
                f"Tổng nợ: <b>{debt.get('debt', 0):,}đ</b>",
                f"Tổng HĐ: {debt.get('total_invoice', 0):,}đ",
                f"Đã trả: {debt.get('total_payment', 0):,}đ",
            ]
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
        except Exception as e:
            log.warning("KiotViet debt fetch failed for customer %s (khID=%s): %s", customer_id, kh_id, e)
            debt = calculate_debt(db_conn, thread_id)
            lines = [
                "<b>📊 Công nợ (local — KiotViet lỗi):</b>",
                f"Tổng: <b>{debt['total']:,}đ</b>",
                f"Đã trả: {debt['paid']:,}đ",
                f"Còn lại: <b>{debt['remaining']:,}đ</b>",
            ]
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_view_debt(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/view_debt": return
        debts = get_all_debts(db_conn)
        if not debts:
            await client.send_message(msg.chat_id, "✅ Không có công nợ nào", reply_to=msg.id)
            return
        await client.send_message(msg.chat_id, _fmt_debt_list(debts), reply_to=msg.id, parse_mode="html")

    # ── HDDT: in tam tinh, global ignore list ────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_in_tam_tinh(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if not re.search(r"(?i)in\s+t[aạ]m\s+t[ií]nh|print\s+provisional", text):
            return
        result = _call_final("/api/order/in-tam-tinh", {
            "text": text,
            "thread_id": _extract_thread_id(msg),
        })
        reply = result.get("reply", "✅ Đã xử lý") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_global_ignore_list(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip().lower()
        if text not in ("global ignore list", "gil"): return
        cur = db_conn.execute("SELECT value FROM kv_store WHERE path = ?", ("hddt_ignore_patterns",))
        row = cur.fetchone()
        patterns = json.loads(row["value"]) if row and row["value"] else []
        if not patterns:
            await client.send_message(msg.chat_id, "📋 Không có pattern nào", reply_to=msg.id)
            return
        lines = ["<b>📋 Pattern bỏ qua HDDT:</b>", ""]
        for p in patterns:
            lines.append(f"• <code>{p}</code>")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── ANALYZE PRODUCTS ────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_analyze_products(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "analyze products": return
        cur = db_conn.execute(
            "SELECT json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL ORDER BY updated_at DESC LIMIT 200"
        )
        product_counts: dict[str, int] = {}
        for row in cur:
            order = json.loads(row["json"])
            items = order.get("items") or order.get("san_pham") or order.get("products") or []
            for item in items:
                name = item.get("name") or item.get("ten") or str(item.get("code", ""))
                name = name.strip()
                if not name or name == "None":
                    continue
                product_counts[name] = product_counts.get(name, 0) + 1
        sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        if not sorted_products:
            await client.send_message(msg.chat_id, "❌ Chưa có dữ liệu sản phẩm", reply_to=msg.id)
            return
        await client.send_message(msg.chat_id, _fmt_analysis(sorted_products), reply_to=msg.id, parse_mode="html")
