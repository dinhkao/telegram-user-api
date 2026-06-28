"""bot_don_hang/flows/nop_wizard.py — Nộp tiền wizard (structured step flow)."""
from telethon import Button

from bot_core import config, db, keyboards
from bot_core.utils import post_json, is_cancel
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


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
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    if w.get("step") == "choose_type":
        if txt == "báo khách nợ" or txt == "bao khach no":
            w["step"] = "choose_ky_toa"
            await event.reply("Chọn", buttons=keyboards.build_nop_wizard_ky_toa_keyboard())
            reset_timer(s.chat_id)
            return
        if txt == "báo khách trả đủ" or txt == "bao khach tra du":
            w["step"] = "wait_photo"
            w["note"] = "tra_tien_mat"
            await event.reply("Hãy gửi hình ảnh chụp tiền mặt và toa", buttons=Button.clear())
            reset_timer(s.chat_id)
            return
        await event.reply("Chọn", buttons=keyboards.build_nop_wizard_type_keyboard())
        reset_timer(s.chat_id)
        return

    if w.get("step") == "choose_ky_toa":
        if txt == "có ký toa" or txt == "co ky toa":
            w["step"] = "wait_photo"
            w["note"] = "co_ky_toa"
            await event.reply("Hãy gửi hình ảnh toa có chữ ký", buttons=Button.clear())
            reset_timer(s.chat_id)
            return
        if txt == "chiều lấy tiền" or txt == "chieu lay tien":
            # Mark as pending with note chieu_lay_tien (no photo)
            thread_id = s.thread_id
            if not thread_id:
                await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
            else:
                await event.reply(f"Đang ghi nhận: chiều lấy tiền cho đơn {s.order_id}...")
                try:
                    await post_json(f"{ORDER_API_BASE}/api/order/nop-tien", {
                        "thread_id": thread_id,
                        "user_id": s.user_id,
                        "note": "chieu_lay_tien",
                        "done": False,
                    })
                    try:
                        fresh = db.get_order(s.order_id)
                        if fresh:
                            s.task_status = fresh.get("task_status")
                    except Exception:
                        pass
                    from bot_core.handlers import send_help
                    await send_help(bot, s.chat_id, s)
                    await event.reply("Đã ghi nhận: chiều lấy tiền")
                except Exception as e:
                    log.error("nop-tien (chieu_lay_tien) error: %s", e)
                    await event.reply(f"Ghi nhận thất bại: {e}")
            s.nop_wizard = None
            reset_timer(s.chat_id)
            return
        if txt == "không ký toa" or txt == "khong ky toa":
            thread_id = s.thread_id
            if not thread_id:
                await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
            else:
                await event.reply(f"Đang xử lý nộp tiền cho đơn {s.order_id}...")
                try:
                    await post_json(f"{ORDER_API_BASE}/api/order/nop-tien", {
                        "thread_id": thread_id,
                        "user_id": s.user_id,
                        "note": "khong_ky_toa",
                    })
                    try:
                        fresh = db.get_order(s.order_id)
                        if fresh:
                            s.task_status = fresh.get("task_status")
                    except Exception:
                        pass
                    from bot_core.handlers import send_help
                    await send_help(bot, s.chat_id, s)
                    await event.reply("Hoàn tất: nộp tiền")
                except Exception as e:
                    log.error("nop-tien (khong_ky_toa) error: %s", e)
                    await event.reply(f"Thao tác nộp tiền thất bại: {e}")
            s.nop_wizard = None
            reset_timer(s.chat_id)
            return
        await event.reply("Chọn", buttons=keyboards.build_nop_wizard_ky_toa_keyboard())
        reset_timer(s.chat_id)
        return


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

    # Forward photo to group
    try:
        caption = f"Nộp tiền • Đơn {s.order_id} • bởi {config.name_of_user_id(s.user_id) or 'n/a'}"
        await bot.send_message(
            config.GROUP_CHAT_ID,
            caption,
            file=event.message.media,
            reply_to=s.thread_id,
        )
    except Exception as e:
        log.warning("Failed to forward nop photo to group: %s", e)

    note = w.get("note", "")
    await event.reply(f"Đang xử lý nộp tiền cho đơn {s.order_id}...")
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/nop-tien", {
            "thread_id": thread_id,
            "user_id": s.user_id,
            "note": note,
        })
        try:
            fresh = db.get_order(s.order_id)
            if fresh:
                s.task_status = fresh.get("task_status")
        except Exception:
            pass
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply("Hoàn tất: nộp tiền")
    except Exception as e:
        log.error("nop-tien (wizard photo) error: %s", e)
        await event.reply(f"Thao tác nộp tiền thất bại: {e}")
    s.nop_wizard = None
    reset_timer(s.chat_id)
    return True
