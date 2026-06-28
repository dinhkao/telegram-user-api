"""bot_handlers/menu_handler.py — Menu button routing & flow delegation."""
import logging
from bot_core import config, keyboards, store
from bot_core.utils import post_json
import bot_flows as flows

log = logging.getLogger("bot.handlers")
ORDER_API_BASE = config.ORDER_API_BASE

async def handle_menu(bot, event, s, text, uid):
    if text == "Xem hóa đơn":
        await flows.handle_show_invoice(bot, event, s)
    elif text == "Tạo HD":
        if not config.is_admin(uid):
            await event.reply("Chức năng chỉ dành cho admin.")
            return
        s.confirm_kv = {"active": True}
        await event.reply("Bạn có chắc chắn tạo hóa đơn Kiotviet?",
            buttons=keyboards.build_kv_confirm_keyboard())
    elif text == "In hóa đơn giao":
        await flows.handle_get_html(bot, event, s)
    elif text == "Xem thông tin":
        await flows.handle_view_info(bot, event, s)
    elif text == "Xem khách hàng":
        await flows.handle_view_customer(bot, event, s)
    elif text == "Sửa tên đơn hàng":
        if not config.is_admin(uid):
            await event.reply("Chức năng chỉ dành cho admin.")
            return
        s.awaiting_rename = True
        await event.reply("Hãy gửi tên đơn hàng mới.", buttons=keyboards.build_rename_keyboard())
    elif text == "Hối":
        if not s.thread_id:
            await event.reply("Không lấy được thread_id.")
            return
        try:
            await post_json(f"{ORDER_API_BASE}/api/order/reply", {"thread_id": s.thread_id, "text": "Hối", "times": 2})
            await event.reply("Đã hối đơn hàng.")
        except Exception as e:
            await event.reply(f"Hối thất bại: {e}")
    else:
        await delegate_flow(bot, event, s, text)

async def delegate_flow(bot, event, s, text):
    if s.edit_invoice and s.edit_invoice.get("active"):
        await flows.handle_invoice_edit_text(bot, event, s, text)
    elif s.confirm_kv and s.confirm_kv.get("active"):
        await flows.handle_kv_confirm_text(bot, event, s, text)
    elif s.pay_flow and s.pay_flow.get("active"):
        await flows.handle_payment_text(bot, event, s, text)
    elif s.nop_wizard and s.nop_wizard.get("active"):
        await flows.handle_nop_wizard_text(bot, event, s, text)
    elif s.confirm_print and s.confirm_print.get("active"):
        await flows.handle_confirm_print_text(bot, event, s, text)
    elif s.awaiting_rename:
        await flows.handle_rename_text(bot, event, s, text)
