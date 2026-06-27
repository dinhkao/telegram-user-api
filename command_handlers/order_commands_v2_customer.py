from __future__ import annotations

import json
import logging
import os
import re
import tempfile

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, add_customer, update_customer
from order_store.customers import search_customers

from .order_commands_v2_delete import handle_delete
from .order_commands_v2_utils import assign_customer, call_final, generate_customer_html
from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


async def _send_customer_file(client, msg, db_conn):
    html_content = generate_customer_html(db_conn)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        tmp_path = f.name
    try:
        await client.send_file(msg.chat_id, tmp_path, reply_to=msg.id, caption="📋 File tìm kiếm khách hàng (live từ database) — mở bằng trình duyệt để tìm và copy ID.")
    finally:
        os.unlink(tmp_path)


def register_order_commands_v2_customer(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_customer_ops(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        lower = text.lower()
        if await handle_delete(client, msg, db_conn):
            return
        if lower.startswith("customer search"):
            query = lower[16:].strip()
            if query:
                results = search_customers(db_conn, query, limit=10)
                if not results:
                    await client.send_message(msg.chat_id, f"❌ Không tìm thấy khách hàng nào tên '{query}'", reply_to=msg.id)
                else:
                    lines = [f"🔍 <b>Tìm thấy {len(results)} khách hàng:</b>", ""]
                    for c in results:
                        name = c.get("name", "N/A")
                        kv_id = c.get("kh_id") or c.get("kiotvietID") or ""
                        note = c.get("note") or c.get("ghi_chu") or ""
                        extra = f" | KV: {kv_id}" if kv_id else ""
                        extra += f" | {note}" if note else ""
                        lines.append(f"• <b>{name}</b> — <code>add khach hang {name}</code>{extra}")
                    await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
                return
            if extract_thread_id(msg):
                await _send_customer_file(client, msg, db_conn)
            return
        m = re.match(r"^add khach hang (.+)$", text, re.IGNORECASE)
        if m:
            arg = m.group(1).strip()
            if arg.startswith("{"):
                try:
                    data = json.loads(arg)
                except json.JSONDecodeError:
                    await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
                    return
                ok, message = add_customer(db_conn, data)
                await client.send_message(msg.chat_id, message, reply_to=msg.id)
                return
            thread_id = extract_thread_id(msg)
            if not thread_id:
                await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
                return
            await assign_customer(client, msg, db_conn, thread_id, arg)
            return
        if lower == "add kl":
            thread_id = extract_thread_id(msg)
            if not thread_id:
                await client.send_message(msg.chat_id, "❌ Không xác định được đơn hàng.", reply_to=msg.id)
                return
            await assign_customer(client, msg, db_conn, thread_id, "2803")
            return
        m = re.match(r"^editkh (\S+)\s+(.+)$", text, re.IGNORECASE)
        if m:
            try:
                data = json.loads(m.group(2))
            except json.JSONDecodeError:
                await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
                return
            ok, message = update_customer(db_conn, m.group(1), data)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
            return
        if lower == "auto complete ban hd":
            thread_id = extract_thread_id(msg)
            if not thread_id:
                return
            result = call_final("/api/order/auto-complete-ban-hd", {"thread_id": thread_id})
            await client.send_message(msg.chat_id, result.get("reply", "✅ Đã tự động hoàn thành") if result else "❌ Lỗi kết nối", reply_to=msg.id)
