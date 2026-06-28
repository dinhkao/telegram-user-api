"""bot_flows/nop_wizard.py — Nộp tiền wizard (structured step flow)."""
from telethon import Button

from bot_core import config, keyboards
from bot_core.utils import is_cancel
from bot_core.store import reset_timer
from ._helpers import log


async def start_nop_wizard(bot, event, s):
    """Start structured nộp tiền wizard."""
    s.nop_wizard = {"active": True, "step": "choose_type", "note": None}
    await event.reply("Chọn", buttons=keyboards.build_nop_wizard_type_keyboard())
    reset_timer(s.chat_id)


async def handle_nop_wizard_text(bot, event, s, text):
    """Handle text input during nộp tiền wizard."""
    w = s.nop_wizard
    if not w or not w.get("active"):
        return
    txt = text.strip().lower()

    if is_cancel(text):
        s.nop_wizard = None
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    if w.get("step") == "choose_type":
        if txt in ("báo khách nợ", "bao khach no"):
            w["step"] = "choose_ky_toa"
            await event.reply("Chọn", buttons=keyboards.build_nop_wizard_ky_toa_keyboard())
            reset_timer(s.chat_id)
            return
        if txt in ("báo khách trả đủ", "bao khach tra du"):
            w["step"] = "wait_photo"
            w["note"] = "tra_tien_mat"
            await event.reply("Hãy gửi hình ảnh chụp tiền mặt và toa", buttons=Button.clear())
            reset_timer(s.chat_id)
            return
        await event.reply("Chọn", buttons=keyboards.build_nop_wizard_type_keyboard())
        reset_timer(s.chat_id)
        return

    if w.get("step") == "choose_ky_toa":
        from bot_flows.nop_wizard_photo import handle_nop_no_photo
        if txt in ("có ký toa", "co ky toa"):
            w["step"] = "wait_photo"
            w["note"] = "co_ky_toa"
            await event.reply("Hãy gửi hình ảnh toa có chữ ký", buttons=Button.clear())
            reset_timer(s.chat_id)
            return
        if txt in ("chiều lấy tiền", "chieu lay tien"):
            await handle_nop_no_photo(bot, event, s, "chieu_lay_tien", "chiều lấy tiền")
            s.nop_wizard = None
            reset_timer(s.chat_id)
            return
        if txt in ("không ký toa", "khong ky toa"):
            await handle_nop_no_photo(bot, event, s, "khong_ky_toa", "không ký toa")
            s.nop_wizard = None
            reset_timer(s.chat_id)
            return
        await event.reply("Chọn", buttons=keyboards.build_nop_wizard_ky_toa_keyboard())
        reset_timer(s.chat_id)
