"""bot_don_hang/flows/kv_confirm.py — KiotViet create confirm text handler."""
from bot_core.store import reset_timer
from .invoice_create import handle_tao_hd


async def handle_kv_confirm_text(bot, event, s, text):
    txt = text.strip().lower()
    if txt == "ok tạo, tôi đã kiểm tra kỹ":
        s.confirm_kv = None
        await handle_tao_hd(bot, event, s)
        return
    if txt == "không, quay lại":
        s.confirm_kv = None
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return
    reset_timer(s.chat_id)
