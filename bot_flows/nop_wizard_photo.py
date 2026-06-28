"""bot_flows/nop_wizard_photo.py — Nộp tiền wizard: photo handling."""
import logging
from bot_core import config, db
from bot_core.utils import mark_task
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE

async def handle_nop_wizard_photo(bot, event, s):
    w = s.nop_wizard
    if not w or not w.get("active") or w.get("step") != "wait_photo":
        return False
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        s.nop_wizard = None
        return True
    try:
        caption = f"Nộp tiền • Đơn {s.order_id} • bởi {config.name_of_user_id(s.user_id) or 'n/a'}"
        await bot.send_message(config.GROUP_CHAT_ID, caption, file=event.message.media, reply_to=s.thread_id)
    except Exception as e:
        log.warning("Failed to forward nop photo: %s", e)
    note = w.get("note", "")
    await event.reply(f"Đang xử lý nộp tiền cho đơn {s.order_id}...")
    ok = await mark_task(s, "nop-tien", s.user_id, note=note)
    if ok:
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply("Hoàn tất: nộp tiền")
    else:
        await event.reply("Thao tác nộp tiền thất bại.")
    s.nop_wizard = None
    reset_timer(s.chat_id)
    return True

async def handle_nop_no_photo(bot, event, s, note, label):
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    await event.reply(f"Đang ghi nhận: {label} cho đơn {s.order_id}...")
    done = note != "chieu_lay_tien"
    ok = await mark_task(s, "nop-tien", s.user_id, note=note, done=done)
    if ok:
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply(f"Đã ghi nhận: {label}")
    else:
        await event.reply(f"Ghi nhận thất bại.")
