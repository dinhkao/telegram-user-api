from __future__ import annotations

import json
import logging
import os
import re
import time

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_order_json

from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_order_commands_v2_debug(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_debug(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        lower = text.lower()
        if lower == "getjson2":
            thread_id = extract_thread_id(msg)
            if not thread_id:
                return
            data = get_order_json(db_conn, thread_id)
            if not data:
                await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
                return
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            snippet = payload[:3800]
            if len(payload) > 3800:
                snippet += "\n... (truncated)"
            await client.send_message(msg.chat_id, f"```json\n{snippet}\n```", reply_to=msg.id, parse_mode="markdown")
            return
        if lower == "test rate limit":
            t0 = time.time()
            for i in range(5):
                await client.send_message(msg.chat_id, f"⚡ Test {i+1}/5 — {time.time()-t0:.2f}s", reply_to=msg.id)
                await client.send_message(msg.chat_id, "💨", reply_to=msg.id)
            await client.send_message(msg.chat_id, f"✅ Done — {time.time()-t0:.2f}s total", reply_to=msg.id)
            return
        if lower == "batcher stats":
            await client.send_message(msg.chat_id, "📊 Batcher: chạy trên Telethon, không giới hạn rate limit", reply_to=msg.id)
            return
        if lower == "flush edits":
            await client.send_message(msg.chat_id, "✅ Telethon không dùng edit queue — edits là realtime", reply_to=msg.id)
            return
        if lower == "cancel edits":
            await client.send_message(msg.chat_id, "✅ Không có edit queue để hủy (Telethon realtime)", reply_to=msg.id)
            return
        if lower == "test edit batching":
            t0 = time.time()
            sent = await client.send_message(msg.chat_id, "🔄 Testing edits...", reply_to=msg.id)
            for i in range(5):
                await sent.edit(f"🔄 Edit {i+1}/5 — {time.time()-t0:.2f}s")
            await sent.edit(f"✅ Edit batching test done — {time.time()-t0:.2f}s")
            await client.send_message(msg.chat_id, "✅ Telethon edits are instant (no queue)", reply_to=msg.id)
            return
        if m := re.match(r"^add pattern (.+)$", text, re.IGNORECASE):
            pattern = m.group(1).strip()
            cur = db_conn.execute("SELECT value FROM kv_store WHERE path = ?", ("hddt_ignore_patterns",))
            row = cur.fetchone()
            patterns = json.loads(row["value"]) if row else []
            if pattern not in patterns:
                patterns.append(pattern)
            db_conn.execute("INSERT INTO kv_store (path, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(path) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", ("hddt_ignore_patterns", json.dumps(patterns, ensure_ascii=False), int(time.time() * 1000)))
            db_conn.commit()
            await client.send_message(msg.chat_id, f"✅ Đã thêm pattern: <code>{pattern}</code>", reply_to=msg.id, parse_mode="html")
            return
        if lower == "?":
            await client.send_message(msg.chat_id, "<b>📋 Lệnh đơn hàng (Telethon):</b>\n\n<b>Task:</b>\n• <code>soan</code> / <code>giao</code> / <code>ban</code>\n• <code>nop</code> / <code>nhan</code> / <code>xuat hd roi</code>\n• <code>clear soan/giao/nop/nhan</code> — Reset\n• <code>skip nop tien</code> — Bỏ qua\n\n<b>Quản lý đơn:</b>\n• <code>del</code> / <code>del hd</code> — Xóa\n• <code>,&lt;mã SP&gt;</code> — Tìm sản phẩm\n• <code>date YYYY-MM-DD</code> / <code>time HH:MM</code>\n\n<b>Khách hàng:</b>\n• <code>customer search</code> / <code>detect customer</code>\n• <code>add khach hang {json}</code>\n• <code>editkh &lt;key&gt; {json}</code>\n\n<b>Task admin:</b>\n• <code>show task</code> / <code>sort tasks</code>\n• <code>check tasks</code> / <code>migrate tasks</code>\n• <code>delete all task</code> / <code>send task notification</code>\n\n<b>Tiền &amp; in ấn:</b>\n• <code>show invoice</code> / <code>print</code>\n• <code>ck &lt;code&gt;</code> / <code>tm &lt;code&gt;</code>\n• <code>/payments</code> / <code>/debt</code> / <code>/view_debt</code>\n• <code>turn on/off money</code> / <code>update debt</code>\n\n<b>Debug:</b>\n• <code>getjson2</code> / <code>get html</code> / <code>?</code>\n• <code>analyze products</code> / <code>test rate limit</code>\n", reply_to=msg.id, parse_mode="html")
