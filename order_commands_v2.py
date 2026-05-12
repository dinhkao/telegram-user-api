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
            result = _call_final("/api/order/mark-deleted", {
                "thread_id": thread_id,
                "user_id": getattr(msg, "sender_id", None),
            })
            reply = result.get("reply", "🗑️ Đã xóa đơn hàng") if result else "❌ Lỗi kết nối"
            await client.send_message(msg.chat_id, reply, reply_to=msg.id)
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
        order = get_order_by_thread_id(db_conn, thread_id)
        order_text = order.get("noi_dung", order.get("name", "")) if order else ""
        results = search_customers(db_conn, order_text)
        if not results:
            results = search_customers(db_conn, "")
        if not results:
            await client.send_message(msg.chat_id, "❌ Không có dữ liệu khách hàng", reply_to=msg.id)
            return
        await client.send_message(msg.chat_id, _fmt_customer_list(results), reply_to=msg.id, parse_mode="html")

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

        # ID mode: "add khach hang 45833" → call assign-customer API
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
            return

        # Run blocking HTTP call in thread pool so it doesn't stall the event loop
        try:
            result = await asyncio.to_thread(
                _call_final, "/api/order/assign-customer", {
                    "thread_id": thread_id,
                    "customer_id": arg,
                    "add_example": True,
                    "user_id": getattr(msg.sender, "id", None) if msg.sender else None,
                }, 60
            )
        except Exception as e:
            log.warning("add khach hang exception: %s", e)
            result = None

        if result and result.get("ok"):
            # Node.js bots will send the actual update message; stay silent
            pass
        elif result and result.get("error"):
            await client.send_message(msg.chat_id, f"❌ Lỗi: {result['error']}", reply_to=msg.id)
        else:
            await client.send_message(msg.chat_id, "❌ Lỗi khi gán khách hàng (timeout hoặc server không phản hồi).", reply_to=msg.id)

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

        # Run blocking HTTP call in thread pool so it doesn't stall the event loop
        try:
            result = await asyncio.to_thread(
                _call_final, "/api/order/assign-customer", {
                    "thread_id": thread_id,
                    "customer_id": "2803",
                    "add_example": True,
                    "update_debt": True,
                    "force_update": True,
                    "user_id": getattr(msg.sender, "id", None) if msg.sender else None,
                }, 60
            )
        except Exception as e:
            log.warning("add kl exception: %s", e)
            result = None

        if result and result.get("ok"):
            # Node.js bots will send the actual update message; stay silent
            pass
        elif result and result.get("error"):
            await client.send_message(msg.chat_id, f"❌ Lỗi add kl: {result['error']}", reply_to=msg.id)
        else:
            await client.send_message(msg.chat_id, "❌ Lỗi khi thực hiện add kl (timeout hoặc server không phản hồi).", reply_to=msg.id)

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

    # ── DETECT CUSTOMER ─────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_detect_customer(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "detect customer": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        result = _call_final("/api/order/detect-customer", {"thread_id": thread_id})
        if not result:
            reply = "❌ Lỗi kết nối đến server xử lý đơn hàng. Vui lòng thử lại."
        elif result.get("reply"):
            reply = result["reply"]
        elif result.get("error"):
            reply = f"⚠️ Lỗi: {result['error']}"
        else:
            reply = "⚠️ Không nhận được phản hồi từ server."
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

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
