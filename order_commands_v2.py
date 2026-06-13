"""order_commands_v2.py — Phase 1+2 handlers: delete, search, task admin, media, price, debug.

Covers ~40 commands previously handled by groupDonHang.js handlers.
Each handler: catches command, reads/writes SQLite, replies via Telethon.
"""
from __future__ import annotations
import asyncio
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
    parse_comma_text,
    save_order_invoice,
    delete_order,
    search_customers,
    add_customer,
    update_customer,
    search_products,
    get_all_tasks,
    delete_all_tasks,
    sort_tasks,
    migrate_tasks_to_v2,
    get_order_json,
    get_order_html,
    set_order_flag,
    _call_final_telegram,
)

from kiotviet import get_customer_debt_kv
log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")


def _extract_thread_id(msg) -> int | None:
    """Extract thread/topic ID from a forum message."""
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
    """Fire-and-forget POST to final_telegram API."""
    return _call_final_telegram(endpoint, body, timeout)


async def _refresh_main_msg(client, conn, thread_id, channel_id, message_id):
    """Refresh main channel message via Telethon edit (no Node.js dependency)."""
    try:
        from order_html import build_order_main_message_html
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        html = build_order_main_message_html(order, thread_id)
        await client.edit_message(
            entity=channel_id,
            message=message_id,
            text=html,
            parse_mode="html",
            link_preview=False,
        )
    except Exception:
        pass


def _generate_customer_html(conn) -> str:
    """Generate a self-contained customer search HTML page from live SQLite data."""
    import html as _html
    from vn import vn_normalize

    rows = conn.execute(
        "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL ORDER BY json_extract(json, '$.name') COLLATE NOCASE"
    ).fetchall()

    items = []
    for row in rows:
        cust = json.loads(row["json"])
        name = cust.get("name", "N/A")
        fb_key = row["firebase_key"]
        kv_id = cust.get("kh_id") or cust.get("kiotvietID") or ""
        note = cust.get("note") or cust.get("ghi_chu") or ""
        name_no_accent = vn_normalize(name)

        note_html = f" | Ghi chú: {_html.escape(note)}" if note else ""
        kv_html = f" | KiotViet ID: {kv_id}" if kv_id else ""

        items.append(f"""                <div class="customer-item" data-name="{_html.escape(name_no_accent)}" data-id="{_html.escape(str(fb_key))}">
                    <div class="customer-info">
                        <div class="customer-name">{_html.escape(name)}</div>
                        <div class="customer-details">
                            ID: {_html.escape(str(fb_key))}{kv_html}{note_html}
                        </div>
                    </div>
                    <button class="copy-button" onclick="copyCommand('{_html.escape(str(fb_key))}', this)">
                        Sao chép lệnh
                    </button>
                </div>""")

    total = len(items)
    items_html = "\n".join(items)

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tìm kiếm khách hàng</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }}
        .container {{ background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; margin-bottom: 30px; }}
        .search-box {{ width: 100%; padding: 15px; font-size: 16px; border: 2px solid #ddd; border-radius: 8px; margin-bottom: 20px; box-sizing: border-box; }}
        .search-box:focus {{ outline: none; border-color: #4CAF50; }}
        .customer-list {{ max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px; }}
        .customer-item {{ padding: 15px; border-bottom: 1px solid #eee; cursor: pointer; transition: background-color 0.2s; display: flex; justify-content: space-between; align-items: center; }}
        .customer-item:hover {{ background-color: #f0f8ff; }}
        .customer-item:last-child {{ border-bottom: none; }}
        .customer-info {{ flex: 1; }}
        .customer-name {{ font-weight: bold; font-size: 16px; color: #333; margin-bottom: 5px; }}
        .customer-details {{ font-size: 14px; color: #666; }}
        .copy-button {{ background-color: #4CAF50; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 14px; }}
        .copy-button:hover {{ background-color: #45a049; }}
        .copied {{ background-color: #28a745 !important; }}
        .no-results {{ text-align: center; padding: 40px; color: #666; font-style: italic; }}
        .stats {{ text-align: center; margin-bottom: 20px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tìm kiếm khách hàng</h1>
        <div class="stats">
            Tổng số khách hàng: <strong id="total-customers">{total}</strong> | 
            Hiển thị: <strong id="showing-customers">{total}</strong>
        </div>
        <input type="text" class="search-box" id="searchBox" placeholder="Nhập tên khách hàng để tìm kiếm..." autofocus>
        <div class="customer-list" id="customerList">
{items_html}
        </div>
    </div>
    <script>
        function copyCommand(id, btn) {{
            navigator.clipboard.writeText(id).then(() => {{
                btn.textContent = 'Đã copy!';
                btn.classList.add('copied');
                setTimeout(() => {{ btn.textContent = 'Sao chép lệnh'; btn.classList.remove('copied'); }}, 1500);
            }}).catch(() => {{
                const ta = document.createElement('textarea');
                ta.value = id;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                btn.textContent = 'Đã copy!';
                btn.classList.add('copied');
                setTimeout(() => {{ btn.textContent = 'Sao chép lệnh'; btn.classList.remove('copied'); }}, 1500);
            }});
        }}
        document.getElementById('searchBox').addEventListener('input', function(e) {{
            const q = e.target.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
            let count = 0;
            document.querySelectorAll('.customer-item').forEach(item => {{
                const name = (item.getAttribute('data-name') || '').toLowerCase();
                if (!q || name.includes(q)) {{ item.style.display = ''; count++; }}
                else {{ item.style.display = 'none'; }}
            }});
            document.getElementById('showing-customers').textContent = count;
        }});
    </script>
</body>
</html>"""


async def _assign_customer(client, msg, db_conn, thread_id: int, kh_id: str):
    """Assign customer to order directly via SQLite + Telethon (no HTTP roundtrip)."""
    from order_db import get_customer_by_key, get_customer_price_list, _save_order, parse_comma_text

    order = get_order_by_thread_id(db_conn, thread_id, )
    if not order:
        await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
        return

    customer = get_customer_by_key(db_conn, str(kh_id))
    if not customer:
        await client.send_message(msg.chat_id, f"❌ Không tìm thấy khách hàng ID: {kh_id}", reply_to=msg.id)
        return

    cust_name = customer.get("name", "N/A")
    cust_phone = customer.get("so_dien_thoai") or customer.get("contactNumber") or ""

    # Update order
    order["khach_hang_id"] = kh_id
    order["customer_name"] = cust_name

    # Re-parse existing invoice with new customer's price list
    order_text = order.get("text") or order.get("text_raw") or ""
    if order_text and order.get("invoice"):
        new_invoice = parse_comma_text(order_text, db_conn, kh_id)
        if new_invoice:
            from product_db import freeze_invoice_cost_prices
            order["invoice"] = freeze_invoice_cost_prices(db_conn, new_invoice)

    if not _save_order(db_conn, thread_id, order):
        await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
        return

    # Build response
    lines = [f"✅ Đã gán khách hàng: <b>{cust_name}</b>"]
    if cust_phone:
        lines.append(f"📱 {cust_phone}")

    # Show invoice with updated prices if any
    invoice = order.get("invoice") or []
    if invoice:
        grand_total = 0
        for item in invoice:
            sp = item.get("sp", "?")
            sl = item.get("sl", 0)
            price = item.get("price", 0)
            sub_total = sl * price
            grand_total += sub_total
            lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>")
        lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")

    await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # Firebase sync + refresh main message (background, non-blocking)
    from firebase_sync import set_order as fb_set_order
    try:
        fb_set_order(thread_id, order)
    except Exception as e:
        log.warning("_assign_customer Firebase sync: %s", e)
    # Schedule main message refresh via Telethon (background)
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if channel_id and message_id:
        asyncio.ensure_future(_refresh_main_msg(client, db_conn, thread_id, channel_id, message_id))


# ── Formatting helpers ─────────────────────────────────────────────

def _fmt_customer_list(results: list[dict]) -> str:
    """Format customer search results as HTML."""
    lines = ["<b>🔍 Tìm khách hàng:</b>", ""]
    for i, c in enumerate(results[:15], 1):
        name = c.get("name") or c.get("ten") or "N/A"
        phone = c.get("so_dien_thoai") or c.get("phone") or ""
        address = c.get("dia_chi") or c.get("address") or ""
        line = f"{i}. <b>{name}</b>"
        if phone:
            line += f" — {phone}"
        if address:
            line += f" — {address[:40]}"
        lines.append(line)
    return "\n".join(lines)


def _fmt_product_list(results: list[dict], query: str) -> str:
    """Format product search results as HTML."""
    lines = [f"<b>📦 Kết quả — {query}:</b>", ""]
    for i, p in enumerate(results[:12], 1):
        name = p.get("name") or p.get("ten") or p.get("productName") or "N/A"
        price = p.get("price") or p.get("gia") or p.get("basePrice") or 0
        code_p = p.get("code") or p.get("ma") or p.get("productCode") or "?"
        unit = p.get("unit") or p.get("don_vi") or ""
        line = f"{i}. <b>[{code_p}]</b> {name}"
        if price:
            line += f" — {int(price):,}đ"
        if unit:
            line += f" / {unit}"
        lines.append(line)
    return "\n".join(lines)


def _fmt_task_list(tasks: list[dict]) -> str:
    """Format task list as HTML."""
    lines = [f"<b>📋 Danh sách task ({len(tasks)}):</b>", ""]
    for t in tasks:
        name = t.get("name") or t["firebase_key"]
        ts = t["task_status"]
        done_keys = [k for k, v in ts.items() if isinstance(v, dict) and (v.get("done") or v.get("skip"))]
        pending_keys = [k for k, v in ts.items() if isinstance(v, dict) and not (v.get("done") or v.get("skip"))]
        v2 = "V2" if t.get("flow_version") == 2 else "V1"
        parts = [f"• <b>{name}</b> ({v2})"]
        if done_keys:
            parts.append(f"✅ {', '.join(done_keys)}")
        if pending_keys:
            parts.append(f"⏳ {', '.join(pending_keys)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


# ── Handler registration ───────────────────────────────────────────

def register_order_commands_v2(client):
    """Register Phase 1+2 handlers for ~40 commands."""
    db_conn = _get_connection()
    log.info("order_commands_v2 listening on chat %d", ORDER_GROUP_ID)

    # ── DELETE ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_del(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if text == "del":
            thread_id = _extract_thread_id(msg)
            if not thread_id:
                await client.send_message(msg.chat_id, "❌ Dùng lệnh này trong topic đơn hàng", reply_to=msg.id)
                return
            ok, message = delete_order(db_conn, thread_id)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
        elif text == "del hd":
            thread_id = _extract_thread_id(msg)
            if not thread_id:
                await client.send_message(msg.chat_id, "❌ Dùng lệnh này trong topic đơn hàng", reply_to=msg.id)
                return
            result = _call_final("/api/order/delete-kiotviet-invoice", {
                "thread_id": thread_id,
                "user_id": getattr(msg, "sender_id", None),
            })
            reply = result.get("reply", "✅ Đã xóa hóa đơn KiotViet") if result else "❌ Lỗi kết nối"
            await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    # ── CUSTOMER ────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_customer_search(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "customer search": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return

        # Generate live HTML from SQLite and send
        import tempfile
        html_content = _generate_customer_html(db_conn)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html_content)
            tmp_path = f.name
        try:
            await client.send_file(
                msg.chat_id,
                tmp_path,
                reply_to=msg.id,
                caption="📋 File tìm kiếm khách hàng (live từ database) — mở bằng trình duyệt để tìm và copy ID.",
            )
        finally:
            os.unlink(tmp_path)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_add_khach_hang(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        # Support both "add khach hang <ID>" and legacy "add khach hang <json>"
        m = re.match(r"^add khach hang (.+)$", text, re.IGNORECASE)
        if not m: return
        arg = m.group(1).strip()

        # Legacy JSON mode (for admin inserting raw customer JSON)
        if arg.startswith("{"):
            try:
                data = json.loads(arg)
            except json.JSONDecodeError:
                await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
                return
            ok, message = add_customer(db_conn, data)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
            return

        # ID mode: "add khach hang 45833" — direct Python (no HTTP to Node.js)
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return

        await _assign_customer(client, msg, db_conn, thread_id, arg)

    # ── ADD KL (quick assign Khách lẻ #2803) ───────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_add_kl(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "add kl": return
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return

        await _assign_customer(client, msg, db_conn, thread_id, "2803")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_editkh(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^editkh (\S+)\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        key = m.group(1)
        try:
            data = json.loads(m.group(2))
        except json.JSONDecodeError:
            await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
            return
        ok, message = update_customer(db_conn, key, data)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── COMMA COMMAND ───────────────────────────────────────────────
    # Disabled: handled by Node.js bot (groupDonHang.js) which has
    # richer features (pattern learning, customer detection DB updates).
    # Remove the return below to re-enable Telethon comma handling.
    # @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    # async def on_comma(event):
    #     ...
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_auto_complete_ban_hd(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "auto complete ban hd": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        result = _call_final("/api/order/auto-complete-ban-hd", {"thread_id": thread_id})
        reply = result.get("reply", "✅ Đã tự động hoàn thành") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    # ── DETECT ALL (customer + invoice) ──────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect_all(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "detect": return
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

        from order_db import detect_customer_free_text, parse_invoice_free_text, _save_order
        from order_db import get_customer_price_list
        from product_db import freeze_invoice_cost_prices

        lines = []

        # Step 1: Detect customer
        detection = detect_customer_free_text(db_conn, order_text)
        kh_id = order.get("khach_hang_id") or order.get("khID")
        assigned = False

        if detection["autoAssign"]:
            cust = detection["autoAssign"]
            order["khach_hang_id"] = cust["customerID"]
            order["customer_name"] = cust["customerName"]
            kh_id = cust["customerID"]
            assigned = True
            lines.append(f"👤 <b>Đã gán:</b> {cust['customerName']} ({cust['score']}%)")
            lines.append(f"🎯 Mẫu: \"{cust['bestMatchedPattern']}\"")
        elif detection["matches"]:
            matches = detection["matches"][:3]
            lines.append(f"🔍 <b>Khách hàng có thể:</b>")
            for i, m in enumerate(matches):
                lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
        else:
            lines.append("👤 Không tìm thấy khách hàng phù hợp.")

        # Step 2: Parse invoice with customer price (or 0 if no customer)
        invoice = parse_invoice_free_text(db_conn, order_text, kh_id)
        if assigned:
            price_list = get_customer_price_list(db_conn, kh_id)
            if price_list:
                invoice = parse_invoice_free_text(db_conn, order_text, kh_id)

        if invoice:
            order["invoice"] = freeze_invoice_cost_prices(db_conn, invoice)
            lines.append(f"\n🎯 <b>Tìm thấy {len(invoice)} sản phẩm:</b>")
            grand_total = 0
            for item in invoice:
                sp = item.get("sp", "?")
                sl = item.get("sl", 0)
                price = item.get("price", 0)
                sub_total = sl * price
                grand_total += sub_total
                lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>")
            lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")
        else:
            lines.append("\n🎯 Không tìm thấy sản phẩm nào.")

        # Save
        _save_order(db_conn, thread_id, order)

        # Refresh main message
        channel_id = order.get("channel_id")
        message_id = order.get("message_id")
        if channel_id and message_id:
            asyncio.ensure_future(_refresh_main_msg(client, db_conn, thread_id, channel_id, message_id))

        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── DETECT CUSTOMER ─────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect_customer(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "detect customer": return
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return

        order = get_order_by_thread_id(db_conn, thread_id, )
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return

        order_text = order.get("text") or order.get("text_raw") or ""
        if not order_text:
            await client.send_message(msg.chat_id, "❌ Đơn hàng này không có nội dung để phân tích.", reply_to=msg.id)
            return

        from order_db import detect_customer_free_text
        detection = detect_customer_free_text(db_conn, order_text)

        if not detection["matches"]:
            await client.send_message(
                msg.chat_id,
                "❌ Chưa có patterns trong database khách hàng hoặc không tìm thấy khách hàng phù hợp.",
                reply_to=msg.id,
            )
            return

        # Auto-assign if high confidence
        if detection["autoAssign"]:
            from order_db import _save_order
            cust = detection["autoAssign"]
            order["khach_hang_id"] = cust["customerID"]
            order["customer_name"] = cust["customerName"]
            _save_order(db_conn, thread_id, order)

            # Refresh main message in channel (background, non-blocking)
            channel_id = order.get("channel_id")
            message_id = order.get("message_id")
            if channel_id and message_id:
                asyncio.ensure_future(_refresh_main_msg(client, db_conn, thread_id, channel_id, message_id))

            reply = (
                f"👤 <b>Đã gán:</b> {cust['customerName']}\n"
                f"🎯 Mẫu: \"{cust['bestMatchedPattern']}\" ({cust['score']}%)\n\n"
                f"✅ Đã lưu vào SQLite. Bấm 'Xem hóa đơn' để kiểm tra."
            )
        else:
            matches = detection["matches"][:5]
            lines = [f"🔍 <b>Tìm thấy {len(detection['matches'])} khách hàng tiềm năng:</b>\n"]
            for i, m in enumerate(matches):
                lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
            reply = "\n".join(lines)

        await client.send_message(msg.chat_id, reply, reply_to=msg.id, parse_mode="html")

    # ── TASK MANAGEMENT ─────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_show_task(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "show task": return
        tasks = get_all_tasks(db_conn)
        if not tasks:
            await client.send_message(msg.chat_id, "📋 Không có task nào", reply_to=msg.id)
            return
        await client.send_message(msg.chat_id, _fmt_task_list(tasks), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_delete_all_task(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "delete all task": return
        count, message = delete_all_tasks(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sort_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "sort tasks": return
        count, message = sort_tasks(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_migrate_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "migrate tasks": return
        count, message = migrate_tasks_to_v2(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_check_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "check tasks": return
        tasks = get_all_tasks(db_conn)
        total = len(tasks)
        v2 = sum(1 for t in tasks if t.get("flow_version") == 2)
        incomplete = sum(
            1 for t in tasks
            if any(
                isinstance(v, dict) and not (v.get("done") or v.get("skip"))
                for v in t["task_status"].values()
            )
        )
        await client.send_message(
            msg.chat_id,
            f"📊 <b>Thống kê task:</b>\nTổng: {total}\nV2: {v2}\nChưa xong: {incomplete}",
            reply_to=msg.id, parse_mode="html",
        )

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_send_task_notification(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "send task notification": return
        result = _call_final("/api/order/send-task-notification", {"chat_id": msg.chat_id})
        reply = result.get("reply", "✅ Đã gửi thông báo") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    # ── PRICE / DISPLAY ─────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_toggle_money(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if text not in ("turn on money", "turn off money"): return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        value = (text == "turn on money")
        ok, message = set_order_flag(db_conn, thread_id, "show_price", value)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_update_debt(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "update debt": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        result = _call_final("/api/order/update-debt", {"thread_id": thread_id})
        reply = result.get("reply", "✅ Đã cập nhật công nợ") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    # ── DATE / TIME ─────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_date(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^date\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        date_val = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        ok, message = set_order_flag(db_conn, thread_id, "date_override", date_val)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_time(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^time\s+(.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        time_val = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        ok, message = set_order_flag(db_conn, thread_id, "time_override", time_val)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── MEDIA ───────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_media(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if not (msg.photo or msg.video): return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        media_type = "photo" if msg.photo else "video"
        log.debug("media: thread=%d type=%s msg_id=%d", thread_id, media_type, msg.id)
        # Media is auto-visible in the topic, no reply needed.
        # final_telegram has its own media handler for saving to Firebase/SQLite.

    # ── REPLY / REPLYSI ─────────────────────────────────────────────
    # Disabled: handled by Node.js bot (groupDonHang.js) which has
    # richer features (multi-line support, xN multiplier, etc.).
    # Remove the return below to re-enable Telethon reply handling.
    # @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    # async def on_reply(event):
    #     ...
    # @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    # async def on_replysi(event):
    #     ...

    # ── ADMIN / DEBUG ───────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_getjson2(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "getjson2": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        data = get_order_json(db_conn, thread_id)
        if not data:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if len(text) > 3800:
            text = text[:3800] + "\n... (truncated)"
        await client.send_message(msg.chat_id, f"```json\n{text}\n```", reply_to=msg.id, parse_mode="markdown")

    # NOTE: `get html` handler removed — migrated to order_commands_v3.py

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_test_rate_limit(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "test rate limit": return
        # Test Telethon speed — send 10 messages as fast as possible
        t0 = time.time()
        for i in range(5):
            await client.send_message(msg.chat_id, f"⚡ Test {i+1}/5 — {time.time()-t0:.2f}s", reply_to=msg.id)
            await client.send_message(msg.chat_id, "💨", reply_to=msg.id)
        await client.send_message(msg.chat_id, f"✅ Done — {time.time()-t0:.2f}s total", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_batcher_stats(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "batcher stats": return
        await client.send_message(msg.chat_id, "📊 Batcher: chạy trên Telethon, không giới hạn rate limit", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_flush_edits(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "flush edits": return
        await client.send_message(msg.chat_id, "✅ Telethon không dùng edit queue — edits là realtime", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_cancel_edits(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "cancel edits": return
        await client.send_message(msg.chat_id, "✅ Không có edit queue để hủy (Telethon realtime)", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_test_edit_batching(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "test edit batching": return
        t0 = time.time()
        sent = await client.send_message(msg.chat_id, "🔄 Testing edits...", reply_to=msg.id)
        for i in range(5):
            await sent.edit(f"🔄 Edit {i+1}/5 — {time.time()-t0:.2f}s")
        await sent.edit(f"✅ Edit batching test done — {time.time()-t0:.2f}s")
        await client.send_message(msg.chat_id, "✅ Telethon edits are instant (no queue)", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_add_pattern(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        m = re.match(r"^add pattern (.+)$", (msg.text or "").strip(), re.IGNORECASE)
        if not m: return
        pattern = m.group(1).strip()
        # Store pattern in kv_store for HDDT detection
        cur = db_conn.execute("SELECT value FROM kv_store WHERE path = ?", ("hddt_ignore_patterns",))
        row = cur.fetchone()
        patterns = []
        if row:
            try:
                patterns = json.loads(row["value"])
            except json.JSONDecodeError:
                pass
        if pattern not in patterns:
            patterns.append(pattern)
        now_ts = int(time.time() * 1000)
        db_conn.execute(
            "INSERT INTO kv_store (path, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(path) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            ("hddt_ignore_patterns", json.dumps(patterns, ensure_ascii=False), now_ts),
        )
        db_conn.commit()
        await client.send_message(msg.chat_id, f"✅ Đã thêm pattern: <code>{pattern}</code>", reply_to=msg.id, parse_mode="html")

    # ── HELP ────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_help(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "?":
            return
        help_text = (
            "<b>📋 Lệnh đơn hàng (Telethon):</b>\n\n"
            "<b>Task:</b>\n"
            "• <code>soan</code> / <code>giao</code> / <code>ban</code>\n"
            "• <code>nop</code> / <code>nhan</code> / <code>xuat hd roi</code>\n"
            "• <code>clear soan/giao/nop/nhan</code> — Reset\n"
            "• <code>skip nop tien</code> — Bỏ qua\n\n"
            "<b>Quản lý đơn:</b>\n"
            "• <code>del</code> / <code>del hd</code> — Xóa\n"
            "• <code>,&lt;mã SP&gt;</code> — Tìm sản phẩm\n"
            "• <code>date YYYY-MM-DD</code> / <code>time HH:MM</code>\n\n"
            "<b>Khách hàng:</b>\n"
            "• <code>customer search</code> / <code>detect customer</code>\n"
            "• <code>add khach hang {json}</code>\n"
            "• <code>editkh &lt;key&gt; {json}</code>\n\n"
            "<b>Task admin:</b>\n"
            "• <code>show task</code> / <code>sort tasks</code>\n"
            "• <code>check tasks</code> / <code>migrate tasks</code>\n"
            "• <code>delete all task</code> / <code>send task notification</code>\n\n"
            "<b>Tiền &amp; in ấn:</b>\n"
            "• <code>show invoice</code> / <code>print</code>\n"
            "• <code>ck &lt;code&gt;</code> / <code>tm &lt;code&gt;</code>\n"
            "• <code>/payments</code> / <code>/debt</code> / <code>/view_debt</code>\n"
            "• <code>turn on/off money</code> / <code>update debt</code>\n\n"
            "<b>Debug:</b>\n"
            "• <code>getjson2</code> / <code>get html</code> / <code>?</code>\n"
            "• <code>analyze products</code> / <code>test rate limit</code>\n"
        )
        await client.send_message(msg.chat_id, help_text, reply_to=msg.id, parse_mode="html")
