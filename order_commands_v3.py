"""order_commands_v3.py — Phase 3: KiotViet invoice, print, payment, debt, analysis handlers."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone, timedelta, UTC

from telethon import events
from telethon.tl.types import MessageService

from order_db import (
    _get_connection,
    get_order_by_thread_id,
    get_customer_kv_id,
    get_customer_by_key,
    search_products,
    _call_final_telegram,
    set_task_status,
    _save_order,
    parse_comma_text,
)
from kiotviet import (
    search_products_kv,
    create_invoice as kv_create_invoice,
    create_kiotviet_invoice,
    get_invoices_by_order,
    get_invoice_detail,
    get_payment_methods,
    process_payment,
    delete_payment_kv,
    create_payment_kv,
    get_customer_debt_kv,
    create_order_with_payment,
)
from payment_db import (
    get_payments,
    add_payment,
    delete_payment_record,
    calculate_debt,
    get_all_debts,
)
from firebase_sync import set_order as fb_set_order
from quy_db import create_fund_receipt
from customer_notify import send_payment_notification
from receipt_print import send_payment_receipt

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


# ── Core payment handler ────────────────────────────────────────────

async def _process_payment_core(thread_id: int, amount: int, user_id: int | None, method: str) -> dict:
    """Core payment processing (DB + KiotViet). Returns result dict for both Telethon and REST API."""
    db_conn = _get_connection()
    actor_name = str(user_id) if user_id else "API"
    account_id = 1 if method == "Transfer" else None
    method_label = "TM" if method == "Cash" else "CK"

    result = {
        "success": False,
        "error": None,
        "thread_id": thread_id,
        "amount": amount,
        "method": method,
        "method_label": method_label,
        "kv_code": None,
        "old_debt": None,
        "new_debt": None,
        "kh_id_fb": None,
        "kv_id": None,
        "kh_name": None,
        "order": None,
    }

    # 1. Read order
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        result["error"] = "Không tìm thấy đơn hàng"
        return result
    result["order"] = order

    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        result["error"] = "Đơn hàng này chưa được gán khách hàng."
        return result
    result["kh_id_fb"] = kh_id_fb

    customer = get_customer_by_key(db_conn, str(kh_id_fb))
    if not customer or not customer.get("kh_id"):
        result["error"] = "Không tìm thấy thông tin khách hàng hoặc ID KiotViet."
        return result

    kv_id = customer["kh_id"]
    kh_name = customer.get("name") or order.get("khach_hang") or str(kh_id_fb)
    result["kv_id"] = kv_id
    result["kh_name"] = kh_name

    # 2. Get old debt from KiotViet (best-effort)
    old_debt = None
    try:
        det = get_customer_debt_kv(kv_id)
        old_debt = det.get("debt")
        result["old_debt"] = old_debt
    except Exception as e:
        log.warning("Could not fetch old debt for customer %d: %s", kv_id, e)

    # 3. Create order + payment on KiotViet
    try:
        kv_res = create_order_with_payment(
            customer_id=kv_id,
            method=method,
            total_payment=amount,
            account_id=account_id,
        )
    except Exception as e:
        log.error("KiotViet create_order_with_payment failed: %s", e)
        result["error"] = f"Lỗi tạo thanh toán KiotViet: {e}"
        return result

    if not kv_res:
        result["error"] = "Không thể tạo thanh toán trên KiotViet"
        return result

    result["kv_code"] = kv_res.get("code", "N/A")

    # 4. Save payment to SQLite
    payment_record = {
        "amount": amount,
        "method": method,
        "kiotvietData": kv_res,
        "createdBy": actor_name,
    }
    ok, payment_msg = add_payment(db_conn, thread_id, payment_record)
    if not ok:
        log.error("Failed to save payment to SQLite: %s", payment_msg)

    # 5. Auto-complete v2 tasks: nhan_tien + nop_tien
    _auto_complete_tasks_core(db_conn, thread_id, user_id)

    # 6. Re-read order after all writes and sync to Firebase
    order = get_order_by_thread_id(db_conn, thread_id)
    result["order"] = order
    try:
        if order:
            fb_set_order(thread_id, order)
    except Exception as e:
        log.warning("Firebase full sync failed: %s", e)

    # 7. Fetch new debt from KiotViet
    new_debt = None
    try:
        det = get_customer_debt_kv(kv_id)
        new_debt = det.get("debt")
        result["new_debt"] = new_debt
    except Exception as e:
        log.warning("Could not fetch new debt for customer %d: %s", kv_id, e)

    result["success"] = True
    return result


async def _handle_payment(client, msg, thread_id: int, amount: int, user_id: int | None, method: str):
    """Process a payment (tm=Cash or ck=Transfer) — fully in Telethon.
    
    Mirrors the Node.js processCashPaymentForOrder() + POST /api/order/payment/* logic.
    """
    # Immediate feedback
    processing_msg = await client.send_message(
        msg.chat_id,
        "⏳ Đang xử lý......",
        reply_to=msg.id,
    )

    result = await _process_payment_core(thread_id, amount, user_id, method)

    if not result["success"]:
        await client.edit_message(msg.chat_id, processing_msg.id, f"❌ {result['error']}")
        return

    method_label = result["method_label"]
    kv_code = result["kv_code"]
    new_debt = result["new_debt"]
    kh_name = result["kh_name"]
    kh_id_fb = result["kh_id_fb"]
    kv_id = result["kv_id"]
    order = result["order"]
    old_debt = result["old_debt"]
    amount = result["amount"]
    method = result["method"]

    # 7. Edit the processing message with success
    await client.edit_message(
        msg.chat_id,
        processing_msg.id,
        f"✅ Đã tạo thanh toán {method_label} thành công {kv_code}",
    )

    # 8. Fund receipt (ONLY for tm/Cash)
    if method == "Cash":
        try:
            create_fund_receipt(
                amount=amount,
                khach_hang_name=kh_name,
                created_by=str(user_id) if user_id else "API",
                client=client,
                order_chat_id=msg.chat_id,
                order_thread_id=thread_id,
            )
        except Exception as e:
            log.warning("Fund receipt creation failed: %s", e)

    # 9. Show new debt
    if new_debt is not None:
        await client.send_message(
            msg.chat_id,
            f"✅ Cập nhật nợ khách hàng -> {new_debt:,}đ",
            reply_to=thread_id,
        )

    # 10. Notify customer topic
    try:
        order_text = order.get("text") or order.get("name") or f"Đơn #{thread_id}"
        send_payment_notification(
            client=client,
            kh_id=str(kh_id_fb),
            thread_id=thread_id,
            amount=amount,
            method=method,
            order_text=order_text,
            old_debt=old_debt,
            new_debt=new_debt,
        )
    except Exception as e:
        log.warning("Customer notification failed: %s", e)

    # 11. Send receipt (async)
    try:
        client.loop.create_task(
            send_payment_receipt(
                client=client,
                thread_id=thread_id,
                customer_name=kh_name,
                payment_amount=amount,
                old_debt=old_debt,
                new_debt=new_debt,
            )
        )
    except Exception as e:
        log.warning("Receipt sending failed: %s", e)

    # 12. Refresh order main message (debounced via batcher)
    try:
        channel_id = order.get("channel_id")
        message_id = order.get("message_id")
        if channel_id and message_id:
            _edit_batcher.schedule(thread_id, channel_id, message_id)
    except Exception as e:
        log.warning("Order message refresh queuing failed: %s", e)


def _auto_complete_tasks_core(db_conn, thread_id: int, user_id: int | None):
    """Auto-complete nhan_tien + nop_tien tasks for the order (DB only)."""
    for task_type in ("nhan_tien", "nop_tien"):
        try:
            ok = set_task_status(db_conn, thread_id, task_type, user_id)
            if ok:
                log.info("Auto-completed task %s for thread %d", task_type, thread_id)
        except Exception as e:
            log.warning("Failed to auto-complete %s for thread %d: %s", task_type, thread_id, e)


def _auto_complete_tasks(client, db_conn, thread_id: int, user_id: int | None, chat_id: int):
    """Auto-complete nhan_tien + nop_tien tasks for the order."""
    _auto_complete_tasks_core(db_conn, thread_id, user_id)


_edit_batcher: _EditBatcher | None = None


async def _refresh_order_message(client, db_conn, thread_id: int, channel_id: int, message_id: int):
    """Rebuild order message HTML and edit in channel via Telethon."""
    try:
        from order_html import build_order_main_message_html
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            return
        html = build_order_main_message_html(order, thread_id)
        if not html:
            return
        await client.edit_message(
            channel_id,
            message_id,
            html,
            parse_mode="html",
        )
        log.info("Order message refreshed: thread=%d msg=%d", thread_id, message_id)
    except Exception as e:
        log.warning("Failed to refresh order message thread=%d: %s", thread_id, e)


def _refresh_order_if_possible(client, db_conn, order: dict):
    """Queue a refresh of the order's main message if channel_id and message_id are known."""
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if not channel_id or not message_id:
        return
    thread_id = order.get("thread_id", 0)
    if _edit_batcher is not None:
        _edit_batcher.schedule(thread_id, channel_id, message_id)
    else:
        # Fallback (should not happen after registration)
        client.loop.create_task(
            _refresh_order_message(client, db_conn, thread_id, channel_id, message_id)
        )


async def _firebase_and_refresh(client, db_conn, thread_id: int, order: dict):
    """Sync to Firebase + refresh main message (runs in background)."""
    try:
        fb_set_order(thread_id, order)
    except Exception as e:
        log.warning("Firebase sync failed: %s", e)
    _refresh_order_if_possible(client, db_conn, order)


def _firebase_refresh_async(client, db_conn, thread_id: int, order: dict):
    """Fire-and-forget Firebase sync + refresh via Telethon event loop."""
    client.loop.create_task(_firebase_and_refresh(client, db_conn, thread_id, order))


# ── Mirror fields: task_type → order root boolean ──────────────────

TASK_MIRROR_FIELDS = {
    "soan_hang": "soan",
    "giao_hang": "giao",
    "nop_tien": "nop",
    "nhan_tien": "nhan",
}


def _sync_task_mirror(order: dict) -> None:
    """Sync task_status done/skip → root boolean fields (soan, giao, nop, nhan)."""
    task_status = order.get("task_status")
    if not task_status or not isinstance(task_status, dict):
        return
    for task_type, field in TASK_MIRROR_FIELDS.items():
        entry = task_status.get(task_type)
        if entry and isinstance(entry, dict):
            order[field] = bool(entry.get("done") or entry.get("skip"))


def _clean_text_chat(order: dict) -> None:
    """Remove cs, cg, cnt, cnhan tokens from text_chat."""
    text_chat = (order.get("text_chat") or "").strip()
    if not text_chat:
        return
    cleaned = " ".join(
        w for w in text_chat.split()
        if w not in ("cs", "cg", "cnt", "cnhan")
    )
    if cleaned != text_chat:
        order["text_chat"] = cleaned


async def _append_kv_debt(client, chat_id: int, reply_msg_id: int, kv_id: int) -> None:
    """Fetch KiotViet debt and append to existing reply message (non-blocking)."""
    try:
        det = get_customer_debt_kv(kv_id)
        debt_val = det.get("debt")
        if debt_val is not None:
            # Read current message text, append debt, edit
            original = await client.get_messages(chat_id, ids=reply_msg_id)
            if original and original.text:
                new_text = original.text + f"\n📊 Nợ hiện tại (KiotViet): {debt_val:,}đ"
                await client.edit_message(chat_id, reply_msg_id, new_text, parse_mode="html")
    except Exception as e:
        log.warning("Failed to append KiotViet debt to reply: %s", e)


async def _send_invoice_html_file(
    client, chat_id: int, thread_id: int,
    invoice_id, invoice_code: str,
    customer_name: str, debt: int = 0,
    *, push_to_print: bool = True,
) -> None:
    """Generate invoice HTML (Node.js style), send as doc + push to printers.
    
    Mirrors Node.js sendInvoiceHTMLFile():
    1. Fetch real invoice from KiotViet API
    2. Generate HTML via inhoadon.generate_invoice_html()
    3. Send as Telegram document
    4. Push to html-to-png (Firebase) for PNG conversion
    5. Push to meta/to_print (Firebase) with write→settle→delete (if push_to_print=True)
    """
    try:
        from inhoadon import generate_invoice_html
        from firebase_sync import _ref as fb_ref

        # Generate HTML using the real KiotViet invoice (same as Node.js)
        html = generate_invoice_html(invoice_id, debt=debt, hints={
            "customerNameOverride": customer_name,
            "expectedVAT": 0,
            "expectedPVC": 0,
            "disableQR": True,
        })

        vn_now = datetime.now(timezone(timedelta(hours=7)))
        file_stamp = vn_now.strftime("%Y%m%d_%H%M%S")

        # 1. Save to temp file + send as Telegram document
        file_name = f"invoice_{invoice_id}_{file_stamp}.html"
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        await client.send_file(
            chat_id,
            file_path,
            caption=f"🧾 Hóa đơn {invoice_code} — {customer_name}",
            reply_to=thread_id,
            force_document=True,
        )

        try:
            os.remove(file_path)
        except OSError:
            pass

        # 2. Push to html-to-png (Firebase) — same as Node.js queueHtmlToPngWithDiscussionMirror
        try:
            ref_png = fb_ref("html-to-png")
            if ref_png:
                ref_png.set({"html": html, "chat_id": chat_id, "message_thread_id": thread_id})
        except Exception as e:
            log.warning("Failed to push invoice to html-to-png: %s", e)

        # 3. Push to meta/to_print (Firebase) with write→settle→delete for physical printer
        # Mirrors Node.js enqueueHtmlForPrint() with print marker injection
        if push_to_print:
            try:
                import asyncio
                ref_print = fb_ref("meta/to_print")
                if ref_print:
                    marker = f"print-queue:{int(time.time()*1000)}-{invoice_id}:copy:1/1"
                    marker_tag = f"<!-- {marker} -->"
                    if "</body>" in html.lower():
                        html_print = html.replace("</body>", f"{marker_tag}\n</body>", 1)
                        html_print = html_print.replace("</BODY>", f"{marker_tag}\n</BODY>", 1)
                    else:
                        html_print = f"{html}\n{marker_tag}"
                    ref_print.set(html_print)
                    await asyncio.sleep(0.12)  # 120ms settle
                    ref_print.delete()
            except Exception as e:
                log.warning("Failed to push invoice to meta/to_print: %s", e)

        log.info("Invoice HTML processed: invoice=%s thread=%d", invoice_code, thread_id)
    except Exception as e:
        log.warning("Failed to send invoice HTML: %s", e)


# ── Edit batcher (prevents FloodWaitError from rapid edits) ─────────
class _EditBatcher:
    """Debounces message edits: only the last edit for a given message wins."""

    def __init__(self, client, db_conn, delay: float = 3.0):
        self.client = client
        self.db_conn = db_conn
        self.delay = delay
        self._pending: dict[tuple[int, int], int] = {}  # (channel_id, message_id): version
        self._lock = asyncio.Lock()

    def schedule(self, thread_id: int, channel_id: int, message_id: int):
        """Schedule a debounced edit.  Multiple calls for the same message collapse into one."""
        key = (channel_id, message_id)
        client_loop = getattr(self.client, "loop", None)
        if client_loop is None:
            return
        # Schedule on the client's event loop
        client_loop.create_task(self._run(thread_id, key))

    async def _run(self, thread_id: int, key: tuple[int, int]):
        async with self._lock:
            version = self._pending.get(key, 0) + 1
            self._pending[key] = version

        await asyncio.sleep(self.delay)

        async with self._lock:
            current = self._pending.get(key)
            if current != version:
                return  # A newer version is pending; let it win
            self._pending.pop(key, None)

        await _refresh_order_message(self.client, self.db_conn, thread_id, key[0], key[1])


# ── Handler registration ────────────────────────────────────────────

def register_order_commands_v3(client):
    """Register Phase 3 handlers: invoice, print, payment, debt, analysis."""
    db_conn = _get_connection()
    global _edit_batcher
    _edit_batcher = _EditBatcher(client, db_conn, delay=3.0)
    log.info("order_commands_v3 listening on chat %d", ORDER_GROUP_ID)

    # ── COMMA INVOICE ───────────────────────────────────────────────
    # Messages starting with , → parse as invoice items
    # Format: comma on its own line, then items below
    #   ,
    #   SP001 2t3b 5 150000 Đỏ
    #   SP002 1t 10
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_comma_invoice(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        raw_text = msg.text or ""
        # Check raw text (before strip) so leading comma on its own line is caught
        if not raw_text.startswith(","): return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        user_id = getattr(msg, "sender_id", None)

        # Remove leading comma(s) and whitespace — match Node.js: text.replace(',', '').trim()
        cleaned = raw_text.lstrip(",").strip()
        if not cleaned:
            return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        if not kh_id_fb:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có khách hàng. Gán khách hàng trước.", reply_to=msg.id)
            return

        # Read customer once (reuse for price list + response)
        customer = get_customer_by_key(db_conn, str(kh_id_fb))
        cust_name = customer.get("name", "N/A") if customer else "N/A"
        cust_kv_id = customer.get("kh_id") if customer else None
        cust_phone = customer.get("contactNumber") if customer else None

        # Parse invoice items (uses get_customer_price_list internally)
        invoice = parse_comma_text(cleaned, db_conn, kh_id_fb)
        if not invoice:
            await client.send_message(msg.chat_id, "❌ Không parse được sản phẩm. Kiểm tra định dạng.", reply_to=msg.id)
            return

        # Save to SQLite (freeze cost prices at order time)
        from product_db import freeze_invoice_cost_prices
        order["invoice"] = freeze_invoice_cost_prices(db_conn, invoice)
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
            return

        # Build response: invoice summary + customer info + price breakdown
        lines = [f"✅ Đã cập nhật {len(invoice)} sản phẩm"]

        # Per-item breakdown
        grand_total = 0
        for item in invoice:
            sp = item.get("sp", "?")
            sl = item.get("sl", 0)
            price = item.get("price", 0)
            sub_total = sl * price
            grand_total += sub_total
            note = item.get("note", "")
            note_suffix = f" — {note}" if note else ""
            lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>{note_suffix}")

        lines.append(f"\n<b>Tổng cộng: {grand_total:,}đ</b>")
        lines.append("")

        if customer:
            lines.append(f"👤 Khách hàng: {cust_name}")
            if cust_phone:
                lines.append(f"📱 SĐT: {cust_phone}")
        else:
            lines.append("⚠️ Khách hàng: Chưa được gán")

        reply_msg = await client.send_message(
            msg.chat_id,
            "\n".join(lines),
            reply_to=thread_id,
            parse_mode="html",
        )

        # Append KiotViet debt to reply (async, non-blocking)
        if cust_kv_id:
            client.loop.create_task(
                _append_kv_debt(client, msg.chat_id, reply_msg.id, cust_kv_id)
            )

        # Firebase sync + refresh (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── TAO HD ──────────────────────────────────────────────────────
    # tao hd / tao hoa don / tao hoadon — create KiotViet invoice
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_tao_hd(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        t = (msg.text or "").strip().lower()
        # Normalize: remove diacritics
        import unicodedata
        t_normalized = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
        if t_normalized not in ("tao hd", "tao hoa don", "tao hoadon"):
            return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        user_id = getattr(msg, "sender_id", None)

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        invoice = order.get("invoice") or order.get("invoice_items") or []
        if not invoice:
            await client.send_message(msg.chat_id, "❌ Không có sản phẩm nào trong đơn hàng. Dùng lệnh `,` để thêm sản phẩm.", reply_to=msg.id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        if not kh_id_fb:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có khách hàng. Gán khách hàng trước.", reply_to=msg.id)
            return

        customer = get_customer_by_key(db_conn, str(kh_id_fb))
        if not customer or not customer.get("kh_id"):
            await client.send_message(msg.chat_id, "❌ Không tìm thấy ID KiotViet của khách hàng.", reply_to=msg.id)
            return

        kv_id = customer["kh_id"]
        kh_name = customer.get("name", "N/A")
        discount = int(order.get("discount", 0))
        pvc = int(order.get("pvc", 0))
        vat = int(order.get("vat", 0))

        # Fetch old debt before creating invoice (best-effort)
        old_debt = None
        try:
            det = get_customer_debt_kv(kv_id)
            old_debt = det.get("debt")
        except Exception as e:
            log.warning("Could not fetch old debt for customer %d: %s", kv_id, e)

        # Processing feedback
        proc_msg = await client.send_message(msg.chat_id, "⏳ Đang tạo hóa đơn KiotViet......", reply_to=msg.id)

        try:
            result = create_kiotviet_invoice(
                customer_id=kv_id,
                invoice_items=invoice,
                discount=discount,
                pvc=pvc,
                vat=vat,
            )
        except Exception as e:
            log.error("KiotViet create invoice failed: %s", e)
            await client.edit_message(msg.chat_id, proc_msg.id, f"❌ Lỗi tạo hóa đơn KiotViet: {e}")
            return

        if not result:
            await client.edit_message(msg.chat_id, proc_msg.id, "❌ Tạo hóa đơn KiotViet thất bại!")
            return

        invoice_code = result.get("code", "N/A")
        invoice_id = result.get("id")

        # Save invoice ID + metadata to SQLite
        order["kiotvietInvoiceID"] = invoice_id
        order["kiotvietInvoiceCode"] = invoice_code
        order["nguoi_tao_HD"] = [user_id or 1809874974]
        snapshot_debt = old_debt if old_debt is not None else 0
        order["invoice_debt_snapshot"] = snapshot_debt
        if old_debt is not None:
            order["khDebt"] = old_debt
        if not _save_order(db_conn, thread_id, order):
            await client.edit_message(msg.chat_id, proc_msg.id, "❌ Lỗi lưu hóa đơn vào database")
            return

        # Auto-complete ban_hd task locally
        set_task_status(db_conn, thread_id, "ban_hd", user_id)
        # Send ban_hd notification directly via Telethon (no Node.js)
        try:
            user_name = "Hệ thống"
            if user_id:
                try: user_name = (await client.get_entity(user_id)).first_name or str(user_id)
                except: pass
            await client.send_message(
                msg.chat_id, f"{user_name} bán HĐ",
                reply_to=thread_id, disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning("ban_hd notification failed: %s", e)

        await client.edit_message(
            msg.chat_id,
            proc_msg.id,
            f"✅ Tạo hóa đơn KiotViet thành công! {invoice_code}\n✅ Đã đánh dấu Bán HĐ hoàn thành",
        )

        # Send invoice HTML file with real debt snapshot (async, non-blocking)
        # tao hd: only html-to-png, NO meta/to_print
        client.loop.create_task(
            _send_invoice_html_file(client, msg.chat_id, thread_id, invoice_id, invoice_code,
                                    kh_name, debt=snapshot_debt, push_to_print=False)
        )

        # Firebase sync + refresh (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── GET HTML ─────────────────────────────────────────────────────
    # get html — resend the invoice HTML file for the current order
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_get_html(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "get html": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        invoice_id = order.get("kiotvietInvoiceID")
        if not invoice_id:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có hóa đơn KiotViet. Dùng lệnh `tao hd` trước.", reply_to=msg.id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        kh_name = "Khách hàng"
        if kh_id_fb:
            customer = get_customer_by_key(db_conn, str(kh_id_fb))
            if customer:
                kh_name = customer.get("name", "Khách hàng")

        invoice_code = order.get("kiotvietInvoiceCode") or str(invoice_id)
        snapshot_debt = order.get("invoice_debt_snapshot", 0)

        await client.send_message(msg.chat_id, "⏳ Đang gửi lại hóa đơn......", reply_to=msg.id)

        # Send invoice HTML file with real debt snapshot (async, non-blocking)
        # get html: only html-to-png, NO meta/to_print (user explicitly requested)
        client.loop.create_task(
            _send_invoice_html_file(client, msg.chat_id, thread_id, invoice_id, invoice_code,
                                    kh_name, debt=snapshot_debt, push_to_print=False)
        )

        # Firebase sync + refresh (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

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
    # Print invoice + delivery ticket (mirrors Node.js /api/order/print-giao)
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_print(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "print": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        user_id = getattr(msg, "sender_id", None)
        
        # Get order from DB
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        
        # Check if order has KiotViet invoice
        invoice_id = order.get("kiotvietInvoiceID")
        if not invoice_id:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có hóa đơn KiotViet. Dùng lệnh `tao hd` trước.", reply_to=msg.id)
            return
        
        # Get customer name
        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        customer_name = "Khách hàng"
        if kh_id_fb:
            customer = get_customer_by_key(db_conn, str(kh_id_fb))
            if customer:
                customer_name = customer.get("name", "Khách hàng")
        
        # Get order text
        order_text = order.get("text", "")
        
        # Get printed by name
        printed_by = str(user_id) if user_id else "Hệ thống"
        
        # Processing feedback
        proc_msg = await client.send_message(msg.chat_id, "⏳ Đang in phiếu giao hàng......", reply_to=msg.id)
        
        try:
            # 1. Print 2 copies of invoice (no QR) via Firebase
            from inhoadon import generate_invoice_html
            from delivery_ticket import _enqueue_html_for_print, generate_delivery_ticket_html
            
            # Get debt snapshot
            snapshot_debt = order.get("invoice_debt_snapshot", 0)
            
            # Generate invoice HTML (no QR)
            invoice_html = generate_invoice_html(invoice_id, debt=snapshot_debt, hints={
                "expectedVAT": int(order.get("vat", 0)),
                "expectedPVC": int(order.get("pvc", 0)),
                "customerNameOverride": customer_name,
                "disableQR": True,
            })
            
            # Queue 2 copies of invoice for printing
            await _enqueue_html_for_print(invoice_html, copies=2)
            
            # 2. Get nộp tiền task URL (if exists)
            nop_tien_topic_url = ""
            try:
                # Query tasks table for nop_tien task
                cur = db_conn.execute(
                    "SELECT json FROM tasks WHERE json_extract(json, '$.dhThreadID') = ? "
                    "AND json_extract(json, '$.taskType') = 'nop_tien' LIMIT 1",
                    (thread_id,)
                )
                task_row = cur.fetchone()
                if task_row:
                    import json
                    task_data = json.loads(task_row["json"])
                    task_thread_id = task_data.get("threadID")
                    if task_thread_id:
                        task_group_id = int(os.getenv("TASK_GROUP_ID", "-1002574612166"))
                        internal_task_group_id = str(task_group_id)[4:] if str(task_group_id).startswith("-100") else str(abs(task_group_id))
                        nop_tien_topic_url = f"tg://privatepost?channel={internal_task_group_id}&post={task_thread_id}"
            except Exception as e:
                log.warning("Failed to get nop_tien task URL: %s", e)
            
            # 3. Generate and print delivery ticket
            delivery_html = generate_delivery_ticket_html(
                thread_id=thread_id,
                customer_name=customer_name,
                order_text=order_text,
                printed_by=printed_by,
                nop_tien_topic_url=nop_tien_topic_url,
            )
            await _enqueue_html_for_print(delivery_html, copies=1)
            
            # 4. Send success message
            await client.edit_message(
                msg.chat_id,
                proc_msg.id,
                f"🖨️ {printed_by} đã in 2 hóa đơn (không QR) và Phiếu giao hàng",
            )
            
        except Exception as e:
            log.error("Print failed: %s", e, exc_info=True)
            await client.edit_message(
                msg.chat_id,
                proc_msg.id,
                f"❌ Lỗi in phiếu: {e}",
            )

    # ── PAYMENT: ck / tm ────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_ck(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^ck\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        amount_str = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        user_id = getattr(msg, "sender_id", None)
        await _handle_payment(client, msg, thread_id, int(amount_str), user_id, "Transfer")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_tm(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^tm\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        amount_str = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        user_id = getattr(msg, "sender_id", None)
        await _handle_payment(client, msg, thread_id, int(amount_str), user_id, "Cash")
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

    # ── UPDATE ───────────────────────────────────────────────────────
    # update — force refresh main order message (via Telethon, no rate limit)
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_update(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "update": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        # Sync task_status mirror to root booleans (soan, giao, nop, nhan)
        _sync_task_mirror(order)
        # Clean text_chat (remove cs, cg, cnt, cnhan)
        _clean_text_chat(order)

        # Save to SQLite
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
            return

        # Fetch channel_id and message_id from DB row (not inside JSON)
        row = db_conn.execute(
            "SELECT channel_id, message_id FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
            (thread_id,),
        ).fetchone()
        channel_id = row["channel_id"] if row else None
        message_id = row["message_id"] if row else None

        # Refresh main message immediately (await so user sees result)
        if channel_id and message_id:
            try:
                await _refresh_order_message(client, db_conn, thread_id, channel_id, message_id)
                await client.send_message(
                    msg.chat_id,
                    "✅ Đã cập nhật lại nội dung đơn hàng",
                    reply_to=msg.id,
                )
            except Exception as e:
                log.warning("update: failed to refresh main message thread=%d: %s", thread_id, e)
                await client.send_message(
                    msg.chat_id,
                    f"⚠️ Đã lưu nhưng không sửa được tin nhắn chính: {e}",
                    reply_to=msg.id,
                )
        else:
            await client.send_message(
                msg.chat_id,
                "✅ Đã cập nhật dữ liệu (không tìm thấy message_id để sửa tin nhắn)",
                reply_to=msg.id,
            )

        # Firebase sync + refresh (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── VAT ─────────────────────────────────────────────────────────
    # vat <amount> — set VAT to specific amount
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_vat_with_amount(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^vat\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        amount_str = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        try:
            amount = int(amount_str)
            if amount < 0:
                await client.send_message(msg.chat_id, "❌ Số tiền VAT không được âm", reply_to=msg.id)
                return
        except ValueError:
            await client.send_message(msg.chat_id, "❌ Số tiền VAT không hợp lệ", reply_to=msg.id)
            return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        order["vat"] = amount
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu VAT", reply_to=msg.id)
            return

        await client.send_message(
            msg.chat_id,
            f"✅ Cập nhật VAT thành công: {amount:,}đ",
            reply_to=msg.id,
        )

        # Sync Firebase + refresh main message (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # vat (no amount) — auto-calculate 8% of invoice total
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_vat_auto(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "vat": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        # Compute 8% of invoice items total
        invoice = order.get("invoice") or order.get("invoice_items") or []
        invoice_total = sum(
            int(item.get("price", 0)) * int(item.get("sl", 0))
            for item in invoice
        )
        new_vat = round(invoice_total * 0.08)

        order["vat"] = new_vat
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu VAT", reply_to=msg.id)
            return

        await client.send_message(
            msg.chat_id,
            f"✅ Cập nhật VAT tự động 8%: {new_vat:,}đ",
            reply_to=msg.id,
        )

        # Sync Firebase + refresh main message (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── BANG GIA CHO / BANG GIA NPP ──────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_bang_gia(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        t = (msg.text or "").strip().lower()
        import unicodedata
        t_norm = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
        price_list_id = None
        label = ""
        if t_norm == "bang gia cho":
            price_list_id = 5
            label = "bảng giá cho"
        elif t_norm == "bang gia npp":
            price_list_id = 160
            label = "bảng giá NPP"
        else:
            return

        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        invoice = order.get("invoice") or order.get("invoice_items") or []
        if not invoice:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có sản phẩm trong hóa đơn.", reply_to=msg.id)
            return

        # Read price list from kv_store (mirrored from Firebase bang_gia_moi)
        cur = db_conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'")
        row = cur.fetchone()
        if not row or not row["value"]:
            await client.send_message(msg.chat_id, f"❌ Không tìm thấy bảng giá ID {price_list_id}.", reply_to=msg.id)
            return

        all_lists = json.loads(row["value"])
        entry = all_lists.get(str(price_list_id))
        if not entry or not isinstance(entry, dict):
            await client.send_message(msg.chat_id, f"❌ Không tìm thấy bảng giá ID {price_list_id}.", reply_to=msg.id)
            return

        price_list = entry.get("price_list")
        if not price_list or not isinstance(price_list, dict):
            await client.send_message(msg.chat_id, f"❌ Bảng giá ID {price_list_id} không có dữ liệu hợp lệ.", reply_to=msg.id)
            return

        matched_count = 0
        changed_count = 0
        missing_codes = []
        detail_rows = []
        next_invoice = []

        for idx, item in enumerate(invoice):
            code = str(item.get("sp") or "").strip().upper()
            qty = int(item.get("sl", 0))
            old_price = int(item.get("price", 0))

            if not code:
                detail_rows.append(f"{idx + 1}. (không có mã) - {qty} x {old_price:,}đ = {(qty * old_price):,}đ")
                next_invoice.append(item)
                continue

            if code not in price_list:
                if code not in missing_codes:
                    missing_codes.append(code)
                detail_rows.append(f"{idx + 1}. {code} - {qty} x {old_price:,}đ = {(qty * old_price):,}đ (giữ giá, không có trong bảng giá)")
                next_invoice.append(item)
                continue

            new_price = price_list[code]
            if not isinstance(new_price, (int, float)):
                detail_rows.append(f"{idx + 1}. {code} - {qty} x {old_price:,}đ = {(qty * old_price):,}đ (giữ giá, giá bảng giá không hợp lệ)")
                next_invoice.append(item)
                continue

            new_price = int(new_price)
            matched_count += 1
            changed = old_price != new_price
            if changed:
                changed_count += 1
            next_item = {**item, "price": new_price}
            line_total = qty * new_price
            detail_rows.append(
                f"{idx + 1}. {code} - {qty} x {old_price:,}đ -> {new_price:,}đ = {line_total:,}đ"
                if changed else
                f"{idx + 1}. {code} - {qty} x {new_price:,}đ = {line_total:,}đ (không đổi)"
            )
            next_invoice.append(next_item)

        if not matched_count:
            await client.send_message(
                msg.chat_id,
                f"⚠️ Không có sản phẩm nào trong đơn khớp bảng giá ID {price_list_id}.",
                reply_to=msg.id,
            )
            return

        # Save updated invoice (freeze cost prices)
        from product_db import freeze_invoice_cost_prices
        order["invoice"] = freeze_invoice_cost_prices(db_conn, next_invoice)
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
            return

        total = sum(int(i.get("sl", 0)) * int(i.get("price", 0)) for i in next_invoice)
        list_name = str(entry.get("name") or entry.get("ten") or "").strip()
        name_part = f"{list_name} (ID {price_list_id})" if list_name else f"ID {price_list_id}"
        reply = f"✅ {label}: áp dụng {name_part}\n"
        reply += f"Khớp {matched_count}/{len(next_invoice)} sản phẩm, đổi giá {changed_count} sản phẩm.\n"
        reply += f"Tổng tạm tính: {total:,}đ"
        if detail_rows:
            reply += f"\n\n📋 Chi tiết từng sản phẩm:\n" + "\n".join(detail_rows)
        if missing_codes:
            reply += f"\nKhông có giá cho: {', '.join(missing_codes[:10])}"
            if len(missing_codes) > 10:
                reply += "…"
        if len(reply) > 3800:
            reply = (
                f"✅ {label}: áp dụng {name_part}\n"
                f"Khớp {matched_count}/{len(next_invoice)} sản phẩm, đổi giá {changed_count} sản phẩm.\n"
                f"Tổng tạm tính: {total:,}đ\n\n"
                f"📋 Chi tiết từng sản phẩm (rút gọn do tin nhắn dài):\n"
                + "\n".join(detail_rows[:30])
                + (f"\n… ({len(detail_rows) - 30} dòng nữa)" if len(detail_rows) > 30 else "")
                + (f"\nKhông có giá cho: {', '.join(missing_codes[:10])}" if missing_codes else "")
            )

        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

        # Refresh main message + Firebase sync (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)
        channel_id = order.get("channel_id")
        message_id = order.get("message_id")
        if channel_id and message_id:
            _edit_batcher.schedule(thread_id, channel_id, message_id)

    # ── BO NO / NO (toggle debt tag) ─────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_bo_no(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        t = (msg.text or "").strip().lower()
        import unicodedata
        t_norm = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
        
        if t_norm == "bo no":
            enabled = False
            reply_text = "Đã bỏ nợ cho đơn này"
        elif t == "no":
            enabled = True
            reply_text = "✅ Đã bật hiển thị nợ cho đơn này"
        else:
            return

        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        order["debt_tag_disabled"] = not enabled
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
            return

        await client.send_message(msg.chat_id, reply_text, reply_to=msg.id)

        # Refresh main message + Firebase sync (non-blocking, debounced)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── DETECT INVOICE ───────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect_invoice(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip().lower() != "detect invoice":
            return

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return

        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        order_text = order.get("text") or order.get("text_raw") or ""
        if not order_text:
            await client.send_message(msg.chat_id, "❌ Đơn hàng này không có nội dung để phân tích.", reply_to=msg.id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")

        from order_db import parse_invoice_free_text
        invoice = parse_invoice_free_text(db_conn, order_text, kh_id_fb)

        if not invoice:
            await client.send_message(
                msg.chat_id,
                f"❌ Không tìm thấy sản phẩm nào trong order text.\n\n📝 Text: \"{order_text[:500]}\"",
                reply_to=msg.id,
            )
            return

        # Save to SQLite
        from product_db import freeze_invoice_cost_prices
        order["invoice"] = freeze_invoice_cost_prices(db_conn, invoice)
        if not _save_order(db_conn, thread_id, order):
            await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
            return

        # Build response
        lines = [f"🎯 TÌM THẤY {len(invoice)} SẢN PHẨM:\n"]
        grand_total = 0
        for item in invoice:
            sp = item.get("sp", "?")
            sl = item.get("sl", 0)
            price = item.get("price", 0)
            sub_total = sl * price
            grand_total += sub_total
            qc_type = item.get("qc_type")
            so_qc = item.get("so_qc", [])
            sl1pc = item.get("sl1pc", 0)
            note = item.get("note", "")

            lines.append(f"• <b>{sp}</b>")
            if qc_type:
                lines.append(f"  📦 QC: {''.join(str(v) for v in so_qc)}{qc_type}")
            lines.append(f"  🔢 SL1PC: {sl1pc}  →  Tổng SL: <b>{sl}</b>")
            if price > 0:
                lines.append(f"  💰 Giá: {price:,}đ  →  Thành tiền: <b>{sub_total:,}đ</b>")
            if note:
                lines.append(f"  📝 {note}")
            lines.append("")

        lines.append(f"💰 <b>Tổng cộng: {grand_total:,}đ</b>")
        lines.append(f"\n✅ Đã lưu {len(invoice)} sản phẩm vào đơn hàng.")

        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

        # Refresh main message + Firebase sync (non-blocking)
        _firebase_refresh_async(client, db_conn, thread_id, order)

    # ── DONE ALL TASKS ───────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_done_all_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip().lower() != "done all tasks":
            return

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Không xác định được topic đơn hàng.",
                reply_to=msg.id,
            )
            return

        user_id = getattr(msg, "sender_id", None)
        TASK_TYPES = ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]

        try:
            # Mark all 5 tasks as done in one batch
            for task_type in TASK_TYPES:
                set_task_status(db_conn, thread_id, task_type, user_id, done=True, skip=False)

            # Re-read order and sync to Firebase + refresh main message
            order = get_order_by_thread_id(db_conn, thread_id)
            if order:
                try:
                    fb_set_order(thread_id, order)
                except Exception as e:
                    log.warning("done_all_tasks Firebase sync failed: %s", e)
                channel_id = order.get("channel_id")
                message_id = order.get("message_id")
                if channel_id and message_id:
                    try:
                        _edit_batcher.schedule(thread_id, channel_id, message_id)
                    except Exception as e:
                        log.warning("done_all_tasks refresh failed: %s", e)

            await client.send_message(
                msg.chat_id,
                "✅ Đã đánh dấu hoàn thành tất cả task.",
                reply_to=msg.id,
            )
        except Exception as e:
            log.error("done_all_tasks error: %s", e, exc_info=True)
            await client.send_message(
                msg.chat_id,
                f"❌ Lỗi khi cập nhật: {e}",
                reply_to=msg.id,
            )
