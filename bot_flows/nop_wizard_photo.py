"""bot_flows/nop_wizard_photo.py — Nộp tiền wizard: photo handling."""
import logging

from bot_core import config, db
from bot_core.utils import post_json
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


async def handle_nop_wizard_photo(bot, event, s):
    """Handle photo sent during nộp tiền wizard wait_photo step."""
    w = s.nop_wizard
    if not w or not w.get("active") or w.get("step") != "wait_photo":
        return False

    thread_id = s.thread_id
    if not thread_id:
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
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/nop-tien", {
            "thread_id": thread_id, "user_id": s.user_id, "note": note,
        })
        try:
            fresh = db.get_order(s.order_id)
            if fresh:
                s.task_status = fresh.get("task_status")
        except Exception:
            pass
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply("Hoàn tất: nộp tiền")
    except Exception as e:
        log.error("nop-tien (wizard photo) error: %s", e)
        await event.reply(f"Thao tác nộp tiền thất bại: {e}")
    s.nop_wizard = None
    reset_timer(s.chat_id)
    return True


async def handle_nop_no_photo(bot, event, s, note, label):
    """Handle nộp tiền without photo (chieu_lay_tien, khong_ky_toa)."""
    thread_id = s.thread_id
    if not thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    await event.reply(f"Đang ghi nhận: {label} cho đơn {s.order_id}...")
    try:
        done = note != "chieu_lay_tien"
        await post_json(f"{ORDER_API_BASE}/api/order/nop-tien", {
            "thread_id": thread_id, "user_id": s.user_id, "note": note, "done": done,
        })
        try:
            fresh = db.get_order(s.order_id)
            if fresh:
                s.task_status = fresh.get("task_status")
        except Exception:
            pass
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply(f"Đã ghi nhận: {label}")
    except Exception as e:
        log.error("nop-tien (%s) error: %s", note, e)
        await event.reply(f"Ghi nhận thất bại: {e}")
