"""bot_don_hang/flows/info.py — View order & customer info."""
from bot_core import db
from bot_core.utils import esc_html
from bot_core.store import reset_timer


async def handle_view_info(bot, event, s):
    order = db.get_order(s.order_id)
    if not order:
        await event.reply("Không tìm thấy đơn hàng.")
        return
    lines = [
        f"<b>Đơn:</b> {esc_html(order.get('text', ''))}",
        f"<b>Khách hàng:</b> {esc_html(order.get('kh', ''))}",
        f"<b>KiotViet ID:</b> {order.get('kiotvietInvoiceID') or 'Chưa có'}",
        f"<b>Thread:</b> {order.get('thread_id')}",
        f"<b>Trạng thái:</b> {order.get('task_status')}",
    ]
    await event.reply("\n".join(lines), parse_mode="html")
    reset_timer(s.chat_id)


async def handle_view_customer(bot, event, s):
    if not s.customer_id:
        await event.reply("Đơn hàng chưa có thông tin khách hàng.")
        return
    cust = db.get_customer_by_key(str(s.customer_id))
    if not cust:
        await event.reply("Không tìm thấy khách hàng.")
        return
    lines = [
        f"<b>Tên:</b> {esc_html(cust.get('name', ''))}",
        f"<b>Phone:</b> {esc_html(cust.get('phone', ''))}",
        f"<b>Địa chỉ:</b> {esc_html(cust.get('address', ''))}",
        f"<b>Nợ:</b> {cust.get('debt', 0)}",
    ]
    await event.reply("\n".join(lines), parse_mode="html")
    reset_timer(s.chat_id)
