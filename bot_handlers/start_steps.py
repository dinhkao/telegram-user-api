"""bot_don_hang/handlers/start_steps.py — /start & task step command handlers."""
import logging

from telethon import events

from bot_core import config, db, store
from bot_core.utils import mark_once, post_json
from .session import start_session, send_help
from .search_list import _send_list_page, _send_search_page, _search_state

ORDER_API_BASE = config.ORDER_API_BASE


def register_start(bot):
    @bot.on(events.NewMessage(pattern=r"^/start(?:\s+(\S+))?"))
    async def h(event):
        if not mark_once(event):
            return
        chat_id = event.chat_id
        uid = event.sender_id
        if not config.is_allowed(uid):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        order_id = (event.pattern_match.group(1) or "").strip()
        if not order_id:
            help_text = (
                "Hãy gửi liên kết có order id:\n"
                "Ví dụ: https://t.me/letrangdonhangbot?start=<order_id>\n\n"
                "Lệnh sử dụng sau khi bắt đầu phiên:\n"
                "- /ban — đánh dấu bán hoá đơn\n"
                "- /soan — đánh dấu soạn hàng xong\n"
                "- /giao — đánh dấu giao hàng xong\n"
                "- /nop_tien — đánh dấu nộp tiền\n"
                "- /nhan_tien — đánh dấu nhận tiền\n"
                "- /show_invoice — xem hoá đơn\n"
                "- /chua_soan — xem danh sách đơn chưa soạn\n"
                "- /chua_giao — xem danh sách đơn chưa giao\n"
                "- /chua_nop_tien — xem danh sách đơn chưa nộp tiền\n\n"
                "Lưu ý: Phiên tự kết thúc sau 1 phút không tương tác."
            )
            await event.reply(help_text)
            return
        try:
            await start_session(bot, chat_id, order_id, uid)
        except Exception as e:
            config_log = logging.getLogger("bot.handlers")
            config_log.error("Start session error: %s", e)
            await event.reply("Xin lỗi, không thể bắt đầu phiên cho đơn này.")


def _make_step(step: str):
    from bot_core.utils import is_cancel  # local import to avoid circular
    import logging
    log = logging.getLogger("bot.handlers")

    async def h(event):
        if not mark_once(event):
            return
        chat_id = event.chat_id
        uid = event.sender_id
        if not config.is_allowed(uid):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        provided = (event.pattern_match.group(1) or "").strip()
        s = store.get(chat_id)
        order_id = provided or (s.order_id if s else None)
        if not order_id:
            await event.reply("Vui lòng bắt đầu bằng liên kết đơn hàng: https://t.me/letrangdonhangbot?start=<order_id>")
            return
        if step == "nhan-tien" and not config.is_admin(uid):
            await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
            return
        if step == "ban":
            await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn để bắt đầu nhập sản phẩm")
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
                if fresh:
                    s.task_status = fresh.get("task_status")
            except Exception as db_err:
                log.warning("SQLite read failed: %s", db_err)
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
        r"^/soan(?:\s+(\S+))?": "soan",
        r"^/giao(?:\s+(\S+))?": "giao",
        r"^/nop_tien(?:\s+(\S+))?": "nop-tien",
        r"^/nhan_tien(?:\s+(\S+))?": "nhan-tien",
    }.items():
        bot.on(events.NewMessage(pattern=pat))(_make_step(step))

    @bot.on(events.NewMessage(pattern=r"^/ban(?:\s+(\S+))?"))
    async def h(event):
        if not mark_once(event):
            return
        await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn để bắt đầu nhập sản phẩm")
