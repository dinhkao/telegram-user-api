"""bot_don_hang/handlers/callbacks.py — Inline button click handlers."""
from telethon import Button, events

from bot_core import config, store


def register_callbacks(bot):
    """Handle inline button clicks (media chooser, invoice edit, KiotViet create)."""
    @bot.on(events.CallbackQuery)
    async def on_callback(event):
        data = event.data.decode() if event.data else ""
        if data.startswith("pt:"):
            from bot_core import media as _media
            await _media.handle_callback_media(bot, event)
            return
        if data.startswith("inv:"):
            await _handle_inv_callback(bot, event)
            return
        if data == "kv:create":
            await _handle_kv_callback(bot, event)


async def _handle_inv_callback(bot, event):
    """Handle inline invoice buttons (inv:edit)."""
    from bot_core import keyboards

    data = event.data.decode() if event.data else ""
    if data != "inv:edit":
        return
    chat_id = event.chat_id
    s = store.get(chat_id)
    if not s or not s.order_id:
        await event.answer("Không có phiên đơn hàng.")
        return
    if not config.is_admin(event.sender_id):
        await event.answer("Chỉ dành cho admin.")
        return
    if s.kv_invoice_id:
        await event.answer("Đơn đã có hóa đơn KiotViet.")
        return

    s.edit_invoice = {"active": True, "draft": [], "step": "choose_code", "current_code": None}
    kb = keyboards.build_codes_keyboard()
    if kb:
        kb.append([Button.text("Huỷ")])
    await event.reply("Nhập hoặc chọn mã sản phẩm:", buttons=kb)
    await event.answer()
    store.reset_timer(chat_id)


async def _handle_kv_callback(bot, event):
    """Handle KiotViet create inline button (kv:create)."""
    data = event.data.decode() if event.data else ""
    if data != "kv:create":
        return
    chat_id = event.chat_id
    s = store.get(chat_id)
    if not s or not s.order_id:
        await event.answer("Không có phiên đơn hàng.")
        return
    if not config.is_admin(event.sender_id):
        await event.answer("Chỉ dành cho admin.")
        return
    if s.kv_invoice_id:
        await event.answer("Đơn đã có hóa đơn KiotViet.")
        return

    s.confirm_kv = {"active": True}
    await event.reply(
        "Bạn có chắc chắn tạo hóa đơn Kiotviet cho đơn hàng này không?",
        buttons=[
            [Button.text("Ok tạo, tôi đã kiểm tra kỹ")],
            [Button.text("Không, quay lại")],
        ],
    )
    await event.answer()
    store.reset_timer(chat_id)
