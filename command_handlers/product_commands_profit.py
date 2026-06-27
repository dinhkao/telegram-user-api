from __future__ import annotations

import json
import os

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_order_by_thread_id
from product_db import calculate_order_profit

from .product_commands_common import extract_thread_id, money, profit

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_product_commands_profit(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_profit(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip().lower()
        if text == "profit all":
            cur = db_conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL ORDER BY updated_at DESC LIMIT 50")
            orders_profit, total_revenue, total_cost, total_profit = [], 0, 0, 0
            for row in cur.fetchall():
                order = json.loads(row[1])
                result = calculate_order_profit(db_conn, order)
                if result["items"]:
                    customer = order.get("customer_name") or order.get("khach_hang") or ""
                    if isinstance(customer, dict):
                        customer = customer.get("name", "")
                    orders_profit.append({"customer": str(customer or ""), "thread_id": row[0], **{k: result[k] for k in ("total_revenue", "total_cost", "total_profit", "items_with_cost", "item_count")}})
                    total_revenue += result["total_revenue"]
                    total_cost += result["total_cost"]
                    total_profit += result["total_profit"]
            if not orders_profit:
                await client.send_message(msg.chat_id, "❌ Chưa có đơn hàng nào có sản phẩm", reply_to=msg.id)
                return
            orders_profit.sort(key=lambda x: x["total_profit"], reverse=True)
            lines = ["<b>📊 Tổng quan lợi nhuận (50 đơn gần nhất)</b>", ""]
            for i, op in enumerate(orders_profit[:15], 1):
                label = op["customer"][:15] if op["customer"] else f"#{op['thread_id']}"
                lines.append(f"{i}. {'🟢' if op['total_profit'] >= 0 else '🔴'} <b>{label}</b>: {profit(op['total_profit'])}")
            if len(orders_profit) > 15:
                lines.append(f"... và {len(orders_profit) - 15} đơn khác")
            lines += ["", "─" * 30, f"📦 Tổng doanh thu: <b>{money(total_revenue)}</b>", f"💵 Tổng giá vốn: <b>{money(total_cost)}</b>", f"{'🟢' if total_profit >= 0 else '🔴'} Tổng lợi nhuận: <b>{profit(total_profit)}</b>"]
            if any(op["items_with_cost"] < op["item_count"] for op in orders_profit):
                lines.append(f"\n⚠️ {sum(1 for op in orders_profit if op['items_with_cost'] < op['item_count'])} đơn có sản phẩm chưa có giá vốn")
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
            return
        if text != "profit":
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Reply vào topic đơn hàng để xem lợi nhuận", reply_to=msg.id)
            return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        result = calculate_order_profit(db_conn, order)
        if not result["items"]:
            await client.send_message(msg.chat_id, "❌ Đơn hàng chưa có sản phẩm", reply_to=msg.id)
            return
        lines = [f"<b>💰 Lợi nhuận đơn hàng #{thread_id}</b>", ""]
        for item in result["items"]:
            if item["has_cost"]:
                lines.append(f"• <code>{item['code']}</code> x{item['qty']}\n  Bán: {money(item['sell_price'])} | Vốn: {money(item['cost_price'])}\n  → {profit(item['profit'])}")
            else:
                lines.append(f"• <code>{item['code']}</code> x{item['qty']}\n  Bán: {money(item['sell_price'])} | Vốn: <i>chưa có</i>\n  → Dùng `sp cost {item['code']} <giá>` để thêm")
        lines += ["", "─" * 30, f"📦 Doanh thu: <b>{money(result['total_revenue'])}</b>", f"💵 Giá vốn: <b>{money(result['total_cost'])}</b>", f"{'🟢' if result['total_profit'] >= 0 else '🔴'} Lợi nhuận: <b>{profit(result['total_profit'])}</b>"]
        if result["items_with_cost"] < result["item_count"]:
            lines.append(f"\n⚠️ {result['item_count'] - result['items_with_cost']} sản phẩm chưa có giá vốn")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
