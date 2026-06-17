"""channel_handler.py — Telethon handler for new orders from the #don_hang channel.

Replaces the Node.js channelDonHangMoi.js 'tạo đơn hàng' flow:
  1. Listen on channel -1002138495144 for new posts
  2. Skip replies, '!' commands, '^' (nhập hàng), '+' (note)
  3. Create forum topic in order group (-1002124542200)
  4. Build V2 order object + save to SQLite + Firebase
  5. Send welcome message + pin in topic
  6. Run auto-parse (customer + invoice detection)
  7. Render channel post with topic link
"""

from __future__ import annotations

import logging
import os
import time
from telethon import events, types
from telethon.tl.functions.messages import CreateForumTopicRequest
from telethon.tl.functions.messages import UpdatePinnedMessageRequest

from order_db import _get_connection, _create_order, _save_order, get_order_by_thread_id
from firebase_sync import set_order as fb_set_order

log = logging.getLogger("channel_handler")

CHANNEL_DON_HANG_MOI = int(os.getenv("CHANNEL_DON_HANG_MOI", "-1002138495144"))
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def _normalize_text(text: str) -> str:
    """Normalize order text — same as Node.js normalizeOrderText + serializeOrderText."""
    return str(text or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def _escape_to_backslash_n(text: str) -> str:
    """Escape newlines to literal \\n — same as Node.js serializeOrderText."""
    return _normalize_text(text).replace("\n", "\\n")


def _build_firebase_key(message_id: int) -> str:
    """Build Firebase key — same as Node.js buildOrderFirebaseKey: dh_{message_id}."""
    return f"dh_{message_id}"


def register(client):
    """Register the channel handler on a Telethon client."""

    @client.on(events.NewMessage(chats=CHANNEL_DON_HANG_MOI))
    async def on_channel_post(event: events.NewMessage.Event):
        msg = event.message

        # Skip non-text, replies, and control/import/note prefixes
        if not msg.text:
            return
        if msg.is_reply:
            return
        if msg.text.startswith("!"):
            return
        if msg.text.startswith("^"):   # nhập hàng — still handled by Node.js
            return
        if msg.text.startswith("+"):   # note — still handled by Node.js
            return

        log.info("New order from channel: msg_id=%d", msg.id)

        # ── 1. Normalize text ────────────────────────────────────────
        order_text = _normalize_text(msg.text)
        text_raw = _escape_to_backslash_n(order_text)
        topic_name = order_text.replace("\\n", " ").replace("\n", " ").strip()
        # Truncate to Telegram's 128-char topic name limit
        if len(topic_name) > 128:
            topic_name = topic_name[:125] + "..."

        firebase_key = _build_firebase_key(msg.id)
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        # ── 2. Create forum topic ─────────────────────────────────────
        try:
            peer = await client.get_input_entity(ORDER_GROUP_ID)
            result = await client(
                CreateForumTopicRequest(
                    peer=peer,
                    title=topic_name,
                    random_id=msg.id,  # deterministic from message_id
                )
            )
        except Exception as e:
            log.error("Failed to create forum topic for msg_id=%d: %s", msg.id, e)
            return

        # Extract message_thread_id from result
        thread_id = None
        for update in getattr(result, "updates", []):
            if isinstance(update, types.UpdateMessageID):
                thread_id = update.id
                break
            if hasattr(update, "message"):
                m = update.message
                if hasattr(m, "reply_to") and m.reply_to:
                    thread_id = getattr(m.reply_to, "reply_to_top_id", None) or m.reply_to.reply_to_msg_id
                if not thread_id and isinstance(m, types.Message):
                    thread_id = m.id
                if thread_id:
                    break

        if not thread_id:
            log.error("Could not extract thread_id from CreateForumTopic result for msg_id=%d", msg.id)
            return

        log.info("Created topic thread_id=%d for channel msg_id=%d", thread_id, msg.id)

        # ── 3. Build V2 order object ──────────────────────────────────
        new_order = {
            "text": order_text,
            "text_raw": text_raw,
            "done": False,
            "created": now_iso,
            "updated_at": now_iso,
            "thread_id": thread_id,
            "firebase_key": firebase_key,
            "channel_id": CHANNEL_DON_HANG_MOI,
            "message_id": msg.id,
            "flow_version": 2,
            "task_status": {
                "ban_hd":    {"done": False, "by": None, "at": None, "skip": False},
                "soan_hang": {"done": False, "by": None, "at": None, "skip": False},
                "giao_hang": {"done": False, "by": None, "at": None, "skip": False},
                "nop_tien":  {"done": False, "by": None, "at": None, "skip": False},
                "nhan_tien": {"done": False, "by": None, "at": None, "skip": False},
            },
            "soan": False,
            "giao": False,
            "nop": False,
            "nhan": False,
        }

        # ── 4. Save to SQLite (primary) + Firebase ────────────────────
        conn = _get_connection()
        _create_order(conn, firebase_key, thread_id, CHANNEL_DON_HANG_MOI, msg.id, new_order)

        # Firebase (background, don't block)
        client.loop.create_task(_firebase_sync(firebase_key, thread_id, msg.id, new_order))

        # ── 5. Send welcome message + pin in topic ────────────────────
        try:
            sent = await client.send_message(
                ORDER_GROUP_ID,
                msg.text,
                reply_to=thread_id,
            )
            pin_msg_id = sent.id
        except Exception as e:
            log.warning("Failed to send welcome message for thread=%d: %s", thread_id, e)
            pin_msg_id = None

        if pin_msg_id:
            client.loop.create_task(_pin_and_update(
                client, conn, firebase_key, thread_id, pin_msg_id
            ))

        # ── 6. Auto-parse (background) ────────────────────────────────
        client.loop.create_task(_auto_parse(client, conn, thread_id, msg.text))

        # ── 7. Render channel post ────────────────────────────────────
        client.loop.create_task(_render_channel_post(client, conn, thread_id, msg.id))


async def _firebase_sync(firebase_key, thread_id, message_id, order):
    """Sync new order to Firebase (3 paths)."""
    try:
        fb_set_order(firebase_key, order)
        # Also store key mappings
        from firebase_sync import firebase_app
        if firebase_app:
            import requests
            base = firebase_app._database_url or ""
            if base:
                requests.put(f"{base}/donhang_order_key_by_thread/{thread_id}.json",
                           json=firebase_key, timeout=5)
                requests.put(f"{base}/donhang_order_key_by_message/{message_id}.json",
                           json=firebase_key, timeout=5)
    except Exception as e:
        log.warning("Firebase sync (background) failed: %s", e)


async def _pin_and_update(client, conn, firebase_key, thread_id, pin_msg_id):
    """Pin welcome message and update firebase_key mapping."""
    try:
        peer = await client.get_input_entity(ORDER_GROUP_ID)
        await client(UpdatePinnedMessageRequest(
            peer=peer,
            id=pin_msg_id,
            unpin=False,
        ))
    except Exception as e:
        log.warning("Pin message failed for thread=%d: %s", thread_id, e)

    try:
        order = get_order_by_thread_id(conn, thread_id)
        if order:
            order["pinMessageID"] = pin_msg_id
            order["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
            _save_order(conn, thread_id, order)
    except Exception as e:
        log.warning("Save pinMessageID failed for thread=%d: %s", thread_id, e)


async def _auto_parse(client, conn, thread_id: int, text: str):
    """Run customer detection + invoice parsing (same as /api/order/auto-parse)."""
    try:
        from order_db import detect_customer_free_text, get_customer_by_key, get_customer_price_list, parse_invoice_free_text
        from product_db import freeze_invoice_cost_prices

        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            log.warning("auto-parse: order not found thread=%d", thread_id)
            return

        kh_id_fb = order.get("khach_hang_id") or order.get("khID")

        # Customer detection
        detection = detect_customer_free_text(conn, text)
        assigned_cust = None
        if detection.get("autoAssign"):
            cust = detection["autoAssign"]
            assigned_cust = cust
            order["khach_hang_id"] = cust["customerID"]
            order["customer_name"] = cust["customerName"]
            kh_id_fb = cust["customerID"]

        # Invoice parsing
        invoice = parse_invoice_free_text(conn, text, kh_id_fb)
        if invoice and assigned_cust:
            price_list = get_customer_price_list(conn, assigned_cust["customerID"])
            if price_list:
                invoice = parse_invoice_free_text(conn, text, assigned_cust["customerID"])

        if invoice:
            order["invoice"] = freeze_invoice_cost_prices(conn, invoice)

        _save_order(conn, thread_id, order)
        log.info("auto-parse: thread=%d items=%d assigned=%s",
                 thread_id, len(invoice) if invoice else 0,
                 assigned_cust["customerName"] if assigned_cust else "none")

        # Build notification
        lines = []
        if invoice:
            lines.append(f"🤖 <b>Auto-detect:</b> đã tìm thấy {len(invoice)} sản phẩm\n")
            grand_total = 0
            for item in invoice:
                sp = item.get("sp", "?")
                sl = item.get("sl", 0)
                price = item.get("price", 0)
                sub_total = sl * price
                grand_total += sub_total
                lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>")
            lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")

        if assigned_cust:
            if lines:
                lines.append("")
            lines.append(f"👤 <b>Đã gán:</b> {assigned_cust['customerName']} ({assigned_cust['score']}%)")
            lines.append(f"🎯 Mẫu: \"{assigned_cust['bestMatchedPattern']}\"")
        elif detection.get("matches"):
            matches = detection["matches"][:3]
            if lines:
                lines.append("")
            lines.append("🔍 <b>Khách hàng có thể:</b>")
            for i, m in enumerate(matches):
                lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")

        if lines:
            try:
                await client.send_message(
                    ORDER_GROUP_ID,
                    "\n".join(lines),
                    reply_to=thread_id,
                    parse_mode="html",
                )
            except Exception as e:
                log.warning("auto-parse notification failed: %s", e)

        # Refresh channel post
        row = conn.execute(
            "SELECT channel_id, message_id FROM orders WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row and row["channel_id"] and row["message_id"]:
            await _render_channel_post(client, conn, thread_id, row["message_id"])

        # Generate picking sheet (phiếu soạn hàng) — auto on new order
        if invoice:
            try:
                from picking_sheet import generate_picking_sheet
                await generate_picking_sheet(client, conn, thread_id)
            except Exception as e:
                log.warning("picking sheet generation failed for thread=%d: %s", thread_id, e)

    except Exception as e:
        log.warning("auto-parse failed for thread=%d: %s", thread_id, e)


async def _render_channel_post(client, conn, thread_id: int, message_id: int):
    """Edit the channel post to show order status with topic link."""
    try:
        from order_html import build_order_main_message_html
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        html = build_order_main_message_html(order, thread_id)
        if not html:
            return
        await client.edit_message(
            CHANNEL_DON_HANG_MOI,
            message_id,
            html,
            parse_mode="html",
        )
        log.info("Channel post rendered: thread=%d msg=%d", thread_id, message_id)
    except Exception as e:
        log.warning("Failed to render channel post thread=%d: %s", thread_id, e)
