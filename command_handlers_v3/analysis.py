from __future__ import annotations

import json
import logging
import re

from telethon import events
from telethon.tl.types import MessageService

from .common import _call_final, _extract_thread_id
from .formatting import _fmt_analysis

log = logging.getLogger("order_commands_v3")


def register_analysis_handlers(client, db_conn):
    @client.on(events.NewMessage(chats=int(__import__("os").getenv("ORDER_GROUP_ID", "-1002124542200"))))
    async def on_orders(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip() != "/orders":
            return
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

    @client.on(events.NewMessage(chats=int(__import__("os").getenv("ORDER_GROUP_ID", "-1002124542200"))))
    async def on_in_tam_tinh(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        if not re.search(r"(?i)in\s+t[aạ]m\s+t[ií]nh|print\s+provisional", text):
            return
        result = _call_final("/api/order/in-tam-tinh", {
            "text": text,
            "thread_id": _extract_thread_id(msg),
        })
        reply = result.get("reply", "✅ Đã xử lý") if result else "❌ Lỗi kết nối"
        await client.send_message(msg.chat_id, reply, reply_to=msg.id)

    @client.on(events.NewMessage(chats=int(__import__("os").getenv("ORDER_GROUP_ID", "-1002124542200"))))
    async def on_global_ignore_list(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip().lower()
        if text not in ("global ignore list", "gil"):
            return
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

    @client.on(events.NewMessage(chats=int(__import__("os").getenv("ORDER_GROUP_ID", "-1002124542200"))))
    async def on_analyze_products(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip() != "analyze products":
            return
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
