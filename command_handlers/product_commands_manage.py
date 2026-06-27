from __future__ import annotations

import os

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection
from product_db import bulk_update_cost_prices, create_products_table, get_all_products, get_product, get_products_from_orders, migrate_products_table, upsert_product

from .product_commands_common import money
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

def register_product_commands_manage(client):
    db_conn = _get_connection()
    create_products_table(db_conn)
    migrate_products_table(db_conn)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_manage(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        lower = text.lower()
        if lower == "sp list":
            products = get_all_products(db_conn)
            if not products:
                await client.send_message(msg.chat_id, "📦 Chưa có sản phẩm nào. Dùng `sp add <mã> <giá_vốn>` để thêm.", reply_to=msg.id)
                return
            lines = ["<b>📦 Danh sách sản phẩm:</b>", ""]
            for p in products:
                lines.append(f"• <code>{p['code']}</code>{' - ' + p['name'] if p.get('name') else ''}: <b>{money(p['cost_price']) if p['cost_price'] > 0 else 'chưa có'}</b>")
            lines += [f"\n📊 Tổng: {len(products)} sản phẩm", "💡 Dùng `sp cost <mã> <giá>` để cập nhật giá vốn"]
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
            return
        if lower.startswith("sp add "):
            parts = text[7:].strip().split()
            if not parts:
                await client.send_message(msg.chat_id, "❌ Cú pháp: `sp add <mã> [giá_vốn] [tên]`", reply_to=msg.id)
                return
            code, cost_price, name = parts[0].upper(), None, None
            if len(parts) > 1:
                try:
                    cost_price = int(parts[1].replace(",", "").replace(".", ""))
                except ValueError:
                    name = " ".join(parts[1:])
            if len(parts) > 2 and cost_price is not None:
                name = " ".join(parts[2:])
            if upsert_product(db_conn, code, name=name, cost_price=cost_price):
                product = get_product(db_conn, code)
                await client.send_message(msg.chat_id, f"✅ Đã thêm/cập nhật sản phẩm <code>{code}</code>\n💰 Giá vốn: <b>{money(product['cost_price']) if product['cost_price'] > 0 else 'chưa có'}</b>", reply_to=msg.id, parse_mode="html")
            else:
                await client.send_message(msg.chat_id, "❌ Lỗi thêm sản phẩm", reply_to=msg.id)
            return
        if lower.startswith("sp cost "):
            parts = text[8:].strip().split()
            if len(parts) < 2:
                await client.send_message(msg.chat_id, "❌ Cú pháp: `sp cost <mã> <giá_vốn>`", reply_to=msg.id)
                return
            try:
                cost_price = int(parts[1].replace(",", "").replace(".", ""))
            except ValueError:
                await client.send_message(msg.chat_id, "❌ Giá không hợp lệ", reply_to=msg.id)
                return
            if upsert_product(db_conn, parts[0].upper(), cost_price=cost_price):
                await client.send_message(msg.chat_id, f"✅ Đã cập nhật giá vốn <code>{parts[0].upper()}</code>: <b>{money(cost_price)}</b>", reply_to=msg.id, parse_mode="html")
            else:
                await client.send_message(msg.chat_id, "❌ Lỗi cập nhật", reply_to=msg.id)
            return
        if lower.startswith("sp bulk"):
            content = text[7:].strip()
            if not content:
                await client.send_message(msg.chat_id, "📋 Cú pháp: Reply tin nhắn này với:\n<code>sp bulk\nSP001 10000\nSP002 15000\nSP003 8000</code>\nHoặc: <code>SP001 10000, SP002 15000</code>", reply_to=msg.id, parse_mode="html")
                return
            updates = []
            for line in content.replace(",", "\n").split("\n"):
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        updates.append({"code": parts[0].upper(), "cost_price": int(parts[1].replace(",", "").replace(".", ""))})
                    except ValueError:
                        pass
            if not updates:
                await client.send_message(msg.chat_id, "❌ Không parse được dữ liệu. Cú pháp: `<mã> <giá>` mỗi dòng", reply_to=msg.id, parse_mode="html")
                return
            count = bulk_update_cost_prices(db_conn, updates)
            lines = [f"✅ Đã cập nhật {count} sản phẩm:"] + [f"• <code>{u['code']}</code>: {money(u['cost_price'])}" for u in updates[:20]]
            if len(updates) > 20:
                lines.append(f"... và {len(updates) - 20} sản phẩm khác")
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
            return
        if lower == "sp sync":
            codes = get_products_from_orders(db_conn)
            added = 0
            for code in codes:
                if not get_product(db_conn, code):
                    upsert_product(db_conn, code, cost_price=0)
                    added += 1
            await client.send_message(msg.chat_id, f"✅ Đã đồng bộ {len(codes)} sản phẩm từ đơn hàng\n📦 Thêm mới: {added} sản phẩm\n💡 Dùng `sp list` để xem và cập nhật giá vốn", reply_to=msg.id)
