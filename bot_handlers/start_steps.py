"""bot_handlers/start_steps.py — /start & task step command handlers."""
import logging
from telethon import events
from bot_core import config, db, store
from bot_core.utils import mark_once, post_json
from .session import start_session, send_help

ORDER_API_BASE = config.ORDER_API_BASE

def register_start(bot):
    @bot.on(events.NewMessage(pattern=r"^/start(?:\s+(\S+))?"))
    async def h(event):
        if not mark_once(event):
            return
        chat_id, uid = event.chat_id, event.sender_id
        if not config.is_allowed(uid):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        order_id = (event.pattern_match.group(1) or "").strip()
        if not order_id:
            await event.reply(
                "Hãy gửi liên kết có order id:\n"
                "Ví dụ: https://t.me/letrangdonhangbot?start=<order_id>\n\n"
                "Lệnh: /ban, /soan, /giao, /nop_tien, /nhan_tien, /show_invoice\n"
                "Lưu ý: Phiên tự kết thúc sau 1 phút không tương tác.")
            return
        try:
            await start_session(bot, chat_id, order_id, uid)
        except Exception as e:
            logging.getLogger("bot.handlers").error("Start session error: %s", e)
            await event.reply("Xin lỗi, không thể bắt đầu phiên cho đơn này.")

def _make_step(step: str):
    from bot_core.utils import is_cancel
    log = logging.getLogger("bot.handlers")
    async def h(event):
        if not mark_once(event):
            return
        chat_id, uid = event.chat_id, event.sender_id
        if not config.is_allowed(uid):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        provided = (event.pattern_match.group(1) or "").strip()
        s = store.get(chat_id)
        order_id = provided or (s.order_id if s else None)
        if not order_id:
            await event.reply("Vui lòng bắt đầu bằng liên kết đơn hàng.")
            return
        if step == "nhan-tien" and not config.is_admin(uid):
            await event.reply("Chức năng chỉ dành cho admin.")
            return
        if step == "ban":
            await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn")
            return
        thread_id = s.thread_id if (s and s.order_id == order_id) else None
        if not thread_id:
            order = db.get_order(order_id)
            thread_id = order.get("thread_id") if order else None
        if not thread_id:
            await event.reply(f"Không lấy được thread_id cho đơn {order_id}.")
            return
        try:
            await post_json(f"{ORDER_API_BASE}/api/order/{step}", {"thread_id": thread_id, "user_id": uid})
            try:
                fresh = db.get_order_by_thread(thread_id)
                if fresh and s:
                    s.task_status = fresh.get("task_status")
            except Exception:
                pass
            await event.reply(f"✅ Đã đánh dấu {step.replace('-', ' ')}.")
            if store.get(chat_id):
                await send_help(bot, chat_id, store.get(chat_id))
            store.reset_timer(chat_id)
        except Exception as e:
            log.error("Step %s error: %s", step, e)
            await event.reply(f"Thao tác thất bại: {e}")
    return h

def register_steps(bot):
    for pat, step in {
        r"^/soan(?:\s+(\S+))?": "soan", r"^/giao(?:\s+(\S+))?": "giao",
        r"^/nop_tien(?:\s+(\S+))?": "nop-tien", r"^/nhan_tien(?:\s+(\S+))?": "nhan-tien",
    }.items():
        bot.on(events.NewMessage(pattern=pat))(_make_step(step))
    @bot.on(events.NewMessage(pattern=r"^/ban(?:\s+(\S+))?"))
    async def h(event):
        if not mark_once(event):
            return
        await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn")
