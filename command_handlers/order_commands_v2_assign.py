from __future__ import annotations

from order_db import _save_order, get_customer_by_key, get_customer_price_list, get_order_by_thread_id, parse_comma_text
from product_db import freeze_invoice_cost_prices

from .order_commands_v2_common import refresh_main_msg


async def assign_customer(client, msg, db_conn, thread_id: int, kh_id: str):
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
        return
    customer = get_customer_by_key(db_conn, str(kh_id))
    if not customer:
        await client.send_message(msg.chat_id, f"❌ Không tìm thấy khách hàng ID: {kh_id}", reply_to=msg.id)
        return
    order["khach_hang_id"], order["customer_name"] = kh_id, customer.get("name", "N/A")
    from order_db import touch_customer_last_order
    touch_customer_last_order(db_conn, kh_id)
    order_text = order.get("text") or order.get("text_raw") or ""
    if order_text and order.get("invoice"):
        new_invoice = parse_comma_text(order_text, db_conn, kh_id)
        if new_invoice:
            order["invoice"] = freeze_invoice_cost_prices(db_conn, new_invoice)
    if not _save_order(db_conn, thread_id, order):
        await client.send_message(msg.chat_id, "❌ Lỗi lưu đơn hàng", reply_to=msg.id)
        return
    # Việc mặc định của khách → auto-thêm vào đơn (dưới 5 việc chuẩn)
    from order_store.custom_tasks import apply_customer_default_tasks
    apply_customer_default_tasks(db_conn, thread_id, kh_id)
    lines = [f"✅ Đã gán khách hàng: <b>{order['customer_name']}</b>"]
    phone = customer.get("so_dien_thoai") or customer.get("contactNumber") or ""
    if phone:
        lines.append(f"📱 {phone}")
    grand_total = 0
    for item in order.get("invoice") or []:
        sub_total = int(item.get("sl", 0) or 0) * int(item.get("price", 0) or 0)
        grand_total += sub_total
        lines.append(f"• <b>{item.get('sp', '?')}</b> x{item.get('sl', 0)} @ {int(item.get('price', 0) or 0):,}đ = <b>{sub_total:,}đ</b>")
    if grand_total:
        lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")
    await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")
    if order.get("channel_id") and order.get("message_id"):
        import asyncio

        asyncio.ensure_future(refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"]))
    from firebase_sync import set_order as fb_set_order

    try:
        fb_set_order(thread_id, order)
    except Exception:
        pass

