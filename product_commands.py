"""product_commands.py — Product management and profit dashboard commands.

Commands:
- sp list: List all products with cost prices
- sp add <code> [cost_price]: Add/update product
- sp cost <code> <price>: Set cost price for product
- sp bulk: Bulk import cost prices from text
- profit: Show profit dashboard for current order
- profit all: Show profit summary for all orders
"""
from __future__ import annotations
import json
import logging
import os

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_order_by_thread_id
from product_db import (
    create_products_table,
    migrate_products_table,
    get_product,
    get_all_products,
    upsert_product,
    delete_product,
    bulk_update_cost_prices,
    calculate_order_profit,
    get_products_from_orders,
)

log = logging.getLogger("product_commands")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def _extract_thread_id(msg) -> int | None:
    """Extract thread_id from message reply."""
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
    return thread_id


def _format_money(n: int) -> str:
    """Format number as Vietnamese đồng."""
    return f"{n:,}đ"


def _format_profit(profit: int) -> str:
    """Format profit with color indicator."""
    if profit > 0:
        return f"+{profit:,}đ"
    elif profit < 0:
        return f"{profit:,}đ"
    return "0đ"


def register_product_commands(client):
    """Register product management and profit commands."""
    db_conn = _get_connection()
    
    # Ensure products table exists
    create_products_table(db_conn)
    migrate_products_table(db_conn)
    
    # ── SP LIST ────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sp_list(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "sp list": return
        
        products = get_all_products(db_conn)
        if not products:
            await client.send_message(
                msg.chat_id,
                "📦 Chưa có sản phẩm nào. Dùng `sp add <mã> <giá_vốn>` để thêm.",
                reply_to=msg.id
            )
            return
        
        lines = ["<b>📦 Danh sách sản phẩm:</b>", ""]
        for p in products:
            cost = _format_money(p["cost_price"]) if p["cost_price"] > 0 else "chưa có"
            name_part = f" - {p['name']}" if p.get("name") else ""
            lines.append(f"• <code>{p['code']}</code>{name_part}: <b>{cost}</b>")
        
        lines.append(f"\n📊 Tổng: {len(products)} sản phẩm")
        lines.append("💡 Dùng `sp cost <mã> <giá>` để cập nhật giá vốn")
        
        await client.send_message(
            msg.chat_id,
            "\n".join(lines),
            reply_to=msg.id,
            parse_mode="html"
        )
    
    # ── SP ADD ─────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sp_add(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        
        text = (msg.text or "").strip()
        if not text.lower().startswith("sp add "): return
        
        parts = text[7:].strip().split()
        if not parts:
            await client.send_message(
                msg.chat_id,
                "❌ Cú pháp: `sp add <mã> [giá_vốn] [tên]`",
                reply_to=msg.id
            )
            return
        
        code = parts[0].upper()
        cost_price = None
        name = None
        
        if len(parts) > 1:
            try:
                cost_price = int(parts[1].replace(",", "").replace(".", ""))
            except ValueError:
                name = " ".join(parts[1:])
        
        if len(parts) > 2 and cost_price is not None:
            name = " ".join(parts[2:])
        
        ok = upsert_product(db_conn, code, name=name, cost_price=cost_price)
        if ok:
            product = get_product(db_conn, code)
            cost_str = _format_money(product["cost_price"]) if product["cost_price"] > 0 else "chưa có"
            await client.send_message(
                msg.chat_id,
                f"✅ Đã thêm/cập nhật sản phẩm <code>{code}</code>\n"
                f"💰 Giá vốn: <b>{cost_str}</b>",
                reply_to=msg.id,
                parse_mode="html"
            )
        else:
            await client.send_message(
                msg.chat_id,
                "❌ Lỗi thêm sản phẩm",
                reply_to=msg.id
            )
    
    # ── SP COST ────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sp_cost(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        
        text = (msg.text or "").strip()
        if not text.lower().startswith("sp cost "): return
        
        parts = text[8:].strip().split()
        if len(parts) < 2:
            await client.send_message(
                msg.chat_id,
                "❌ Cú pháp: `sp cost <mã> <giá_vốn>`",
                reply_to=msg.id
            )
            return
        
        code = parts[0].upper()
        try:
            cost_price = int(parts[1].replace(",", "").replace(".", ""))
        except ValueError:
            await client.send_message(
                msg.chat_id,
                "❌ Giá không hợp lệ",
                reply_to=msg.id
            )
            return
        
        ok = upsert_product(db_conn, code, cost_price=cost_price)
        if ok:
            await client.send_message(
                msg.chat_id,
                f"✅ Đã cập nhật giá vốn <code>{code}</code>: <b>{_format_money(cost_price)}</b>",
                reply_to=msg.id,
                parse_mode="html"
            )
        else:
            await client.send_message(
                msg.chat_id,
                "❌ Lỗi cập nhật",
                reply_to=msg.id
            )
    
    # ── SP BULK ────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sp_bulk(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        
        text = (msg.text or "").strip()
        if not text.lower().startswith("sp bulk"): return
        
        # Get the content after "sp bulk"
        content = text[7:].strip()
        if not content:
            await client.send_message(
                msg.chat_id,
                "📋 Cú pháp: Reply tin nhắn này với:\n"
                "<code>sp bulk\nSP001 10000\nSP002 15000\nSP003 8000</code>\n"
                "Hoặc: <code>SP001 10000, SP002 15000</code>",
                reply_to=msg.id,
                parse_mode="html"
            )
            return
        
        # Parse bulk input
        updates = []
        for line in content.replace(",", "\n").split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                code = parts[0].upper()
                try:
                    cost = int(parts[1].replace(",", "").replace(".", ""))
                    updates.append({"code": code, "cost_price": cost})
                except ValueError:
                    continue
        
        if not updates:
            await client.send_message(
                msg.chat_id,
                "❌ Không parse được dữ liệu. Cú pháp: `<mã> <giá>` mỗi dòng",
                reply_to=msg.id,
                parse_mode="html"
            )
            return
        
        count = bulk_update_cost_prices(db_conn, updates)
        
        # Show results
        lines = [f"✅ Đã cập nhật {count} sản phẩm:"]
        for u in updates[:20]:  # Show max 20
            lines.append(f"• <code>{u['code']}</code>: {_format_money(u['cost_price'])}")
        if len(updates) > 20:
            lines.append(f"... và {len(updates) - 20} sản phẩm khác")
        
        await client.send_message(
            msg.chat_id,
            "\n".join(lines),
            reply_to=msg.id,
            parse_mode="html"
        )
    
    # ── SP SYNC ────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sp_sync(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "sp sync": return
        
        # Get all product codes from orders
        codes = get_products_from_orders(db_conn)
        
        added = 0
        for code in codes:
            existing = get_product(db_conn, code)
            if not existing:
                upsert_product(db_conn, code, cost_price=0)
                added += 1
        
        await client.send_message(
            msg.chat_id,
            f"✅ Đã đồng bộ {len(codes)} sản phẩm từ đơn hàng\n"
            f"📦 Thêm mới: {added} sản phẩm\n"
            f"💡 Dùng `sp list` để xem và cập nhật giá vốn",
            reply_to=msg.id
        )
    
    # ── PROFIT (current order) ─────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_profit(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "profit": return
        
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Reply vào topic đơn hàng để xem lợi nhuận",
                reply_to=msg.id
            )
            return
        
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(
                msg.chat_id,
                "❌ Không tìm thấy đơn hàng",
                reply_to=msg.id
            )
            return
        
        result = calculate_order_profit(db_conn, order)
        
        if not result["items"]:
            await client.send_message(
                msg.chat_id,
                "❌ Đơn hàng chưa có sản phẩm",
                reply_to=msg.id
            )
            return
        
        # Build profit report
        lines = [f"<b>💰 Lợi nhuận đơn hàng #{thread_id}</b>", ""]
        
        # Item details
        for item in result["items"]:
            profit_str = _format_profit(item["profit"])
            cost_str = _format_money(item["cost_price"]) if item["has_cost"] else "?"
            
            if item["has_cost"]:
                lines.append(
                    f"• <code>{item['code']}</code> x{item['qty']}\n"
                    f"  Bán: {_format_money(item['sell_price'])} | Vốn: {cost_str}\n"
                    f"  → {profit_str}"
                )
            else:
                lines.append(
                    f"• <code>{item['code']}</code> x{item['qty']}\n"
                    f"  Bán: {_format_money(item['sell_price'])} | Vốn: <i>chưa có</i>\n"
                    f"  → Dùng `sp cost {item['code']} <giá>` để thêm"
                )
        
        # Summary
        lines.append("")
        lines.append("─" * 30)
        lines.append(f"📦 Doanh thu: <b>{_format_money(result['total_revenue'])}</b>")
        lines.append(f"💵 Giá vốn: <b>{_format_money(result['total_cost'])}</b>")
        
        profit_emoji = "🟢" if result["total_profit"] >= 0 else "🔴"
        lines.append(f"{profit_emoji} Lợi nhuận: <b>{_format_profit(result['total_profit'])}</b>")
        
        if result["items_with_cost"] < result["item_count"]:
            missing = result["item_count"] - result["items_with_cost"]
            lines.append(f"\n⚠️ {missing} sản phẩm chưa có giá vốn")
        
        await client.send_message(
            msg.chat_id,
            "\n".join(lines),
            reply_to=msg.id,
            parse_mode="html"
        )
    
    # ── PROFIT ALL ─────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_profit_all(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip().lower() != "profit all": return
        
        # Get recent orders
        cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL ORDER BY updated_at DESC LIMIT 50"
        )
        
        orders_profit = []
        total_revenue = 0
        total_cost = 0
        total_profit = 0
        
        for row in cur.fetchall():
            thread_id = row[0]
            order = json.loads(row[1])
            
            result = calculate_order_profit(db_conn, order)
            if result["items"]:
                customer = order.get("customer_name") or order.get("khach_hang") or ""
                if isinstance(customer, dict):
                    customer = customer.get("name", "")
                customer = str(customer or "")
                orders_profit.append({
                    "customer": customer,
                    "revenue": result["total_revenue"],
                    "cost": result["total_cost"],
                    "profit": result["total_profit"],
                    "items_with_cost": result["items_with_cost"],
                    "item_count": result["item_count"],
                })
                total_revenue += result["total_revenue"]
                total_cost += result["total_cost"]
                total_profit += result["total_profit"]
        
        if not orders_profit:
            await client.send_message(
                msg.chat_id,
                "❌ Chưa có đơn hàng nào có sản phẩm",
                reply_to=msg.id
            )
            return
        
        # Sort by profit descending
        orders_profit.sort(key=lambda x: x["profit"], reverse=True)
        
        lines = ["<b>📊 Tổng quan lợi nhuận (50 đơn gần nhất)</b>", ""]
        
        # Top profitable orders
        for i, op in enumerate(orders_profit[:15], 1):
            profit_str = _format_profit(op["profit"])
            emoji = "🟢" if op["profit"] >= 0 else "🔴"
            customer = op["customer"][:15] if op["customer"] else f"#{op['thread_id']}"
            lines.append(f"{i}. {emoji} <b>{customer}</b>: {profit_str}")
        
        if len(orders_profit) > 15:
            lines.append(f"... và {len(orders_profit) - 15} đơn khác")
        
        # Summary
        lines.append("")
        lines.append("─" * 30)
        lines.append(f"📦 Tổng doanh thu: <b>{_format_money(total_revenue)}</b>")
        lines.append(f"💵 Tổng giá vốn: <b>{_format_money(total_cost)}</b>")
        
        profit_emoji = "🟢" if total_profit >= 0 else "🔴"
        lines.append(f"{profit_emoji} Tổng lợi nhuận: <b>{_format_profit(total_profit)}</b>")
        
        # Missing cost info
        orders_missing = sum(1 for op in orders_profit if op["items_with_cost"] < op["item_count"])
        if orders_missing:
            lines.append(f"\n⚠️ {orders_profit.__len__()} đơn có sản phẩm chưa có giá vốn")
        
        await client.send_message(
            msg.chat_id,
            "\n".join(lines),
            reply_to=msg.id,
            parse_mode="html"
        )
    
    log.info("product_commands registered on chat %d", ORDER_GROUP_ID)
