"""bot_don_hang/handlers/reply_actions.py — Reply keyboard actions router."""
import logging
import re

from telethon import Button, events
from telethon.tl.types import MessageService

from bot_core import config, db, keyboards, store
from bot_core.utils import mark_once, post_json, is_cancel
import bot_flows as flows
from .session import send_help
from .search_list import _send_list_page, _send_search_page, _send_order_detail, _search_state, _search_page, _list_state
from .start_steps import register_start, register_steps
from .sheets import register_sheet_commands
from .media_events import register_media_handlers
from .callbacks import register_callbacks

log = logging.getLogger("bot.handlers")
ORDER_API_BASE = config.ORDER_API_BASE


def register_show_invoice(bot):
    @bot.on(events.NewMessage(pattern=r"^/show_invoice(?:\s+(\S+))?"))
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
        if not order_id or not s or order_id != s.order_id:
            await event.reply("Vui lòng bắt đầu bằng liên kết đơn hàng: https://t.me/letrangdonhangbot?start=<order_id>")
            return
        await flows.handle_show_invoice(bot, event, s)


def register_reply_actions(bot):
    @bot.on(events.NewMessage)
    async def h(event):
        if isinstance(event.message, MessageService):
            return
        text = (event.message.text or "").strip()
        chat_id = event.chat_id
        uid = event.sender_id
        if not config.is_allowed(uid):
            return
        # List — show orders without giao_hang from last 30 days (paginated)
        if text.strip().lower() == "list":
            if not mark_once(event):
                return
            await _send_list_page(bot, event, chat_id, page=1)
            return

        # /s <keyword> — search orders (accent-insensitive, works without session)
        if text.lower().startswith("/s "):
            if not mark_once(event):
                return
            keyword = text[3:].strip()
            if not keyword:
                await event.reply("Cú pháp: /s <từ khóa>")
                return
            _search_state[chat_id] = keyword
            _search_page[chat_id] = 1
            await _send_search_page(bot, event, 1, keyword)
            return

        s = store.get(chat_id)
        if not s:
            return
        store.reset_timer(chat_id)
        if not mark_once(event):
            return

        log.info("Reply text=%r uid=%s chat=%s", text, uid, chat_id)

        # Cancel
        if is_cancel(text):
            log.info("Cancel detected for uid=%s chat=%s", uid, chat_id)
            s.edit_invoice = None
            s.confirm_kv = None
            s.confirm_payment = None
            s.confirm_giao = None
            s.confirm_print = None
            s.pay_flow = None
            s.nop_wizard = None
            s.awaiting_rename = False
            await event.reply("Đã huỷ thao tác.")
            try:
                await send_help(bot, chat_id, s)
            except Exception as e:
                log.error("send_help after cancel failed: %s", e)
                await event.reply("Không gửi được bàn phím mới.")
            return

        # Quay lại button after invoice update
        if text.strip().lower() == "quay lại":
            await send_help(bot, chat_id, s)
            return

        # Tạo hóa đơn Kiotviet luôn! button after invoice update
        if text.strip().lower() == "tạo hóa đơn kiotviet luôn!":
            if not config.is_admin(uid):
                await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
                return
            s.confirm_kv = {"active": True}
            await event.reply(
                "Bạn có chắc chắn tạo hóa đơn Kiotviet cho đơn hàng này không?",
                buttons=keyboards.build_kv_confirm_keyboard(),
            )
            return

        # Clear own actions
        clear_map = {
            "Huỷ bán": "ban_hd",
            "Huỷ soạn": "soan_hang",
            "Huỷ giao": "giao_hang",
            "Huỷ nộp": "nop_tien",
            "Huỷ nhận": "nhan_tien",
        }
        if text in clear_map:
            key = clear_map[text]
            entry = (s.task_status or {}).get(key) or {}
            if not entry.get("done"):
                await event.reply("Thao tác nãy chưa được đánh dấu hoàn thành.")
                return
            if str(uid) != str(entry.get("by") or ""):
                by_name = config.name_of_user_id(entry.get("by")) or "người khác"
                await event.reply(f"Chỉ {by_name} mới có thể huỷ thao tác này.")
                return
            if s.thread_id:
                try:
                    resp = await post_json(f"{ORDER_API_BASE}/api/order/{s.thread_id}/task_status/clear", {"type": key})
                    log.info("task_status/clear response: %s", resp)
                    try:
                        fresh = db.get_order_by_thread(s.thread_id)
                        if fresh:
                            s.task_status = fresh.get("task_status")
                    except Exception as db_err:
                        log.warning("SQLite read failed: %s", db_err)
                    await send_help(bot, chat_id, s)
                except Exception as e:
                    log.error("Clear %s error: %s", key, e)
                    await event.reply(f"Huỷ thất bại: {e}")
            return

        # Action buttons
        action_map = {
            "Bán HD": "ban",
            "Soạn hàng": "soan",
            "Giao hàng": "giao",
            "Nộp tiền": "nop-tien",
            "Nhận tiền": "nhan-tien",
        }
        if text in action_map:
            step = action_map[text]
            if step == "ban":
                await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn để bắt đầu nhập sản phẩm")
                return
            if step == "giao":
                if not s.thread_id:
                    await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
                    return
                try:
                    await post_json(f"{ORDER_API_BASE}/api/order/giao", {"thread_id": s.thread_id, "user_id": uid})
                    try:
                        fresh = db.get_order_by_thread(s.thread_id)
                        if fresh:
                            s.task_status = fresh.get("task_status")
                    except Exception as db_err:
                        log.warning("SQLite read failed: %s", db_err)
                    await event.reply("✅ Đã đánh dấu giao hàng.")
                    await send_help(bot, chat_id, s)
                except Exception as e:
                    log.error("giao error: %s", e)
                    await event.reply(f"Thao tác thất bại: {e}")
                return
            if step == "nop-tien":
                await flows.start_nop_wizard(bot, event, s)
                return
            if step == "nhan-tien":
                await flows.start_payment_flow(bot, event, s)
                return
            if not s.thread_id:
                await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
                return
            try:
                await post_json(f"{ORDER_API_BASE}/api/order/{step}", {"thread_id": s.thread_id, "user_id": uid})
                try:
                    fresh = db.get_order_by_thread(s.thread_id)
                    if fresh:
                        s.task_status = fresh.get("task_status")
                except Exception as db_err:
                    log.warning("SQLite read failed: %s", db_err)
                await event.reply(f"✅ Đã đánh dấu {text}.")
                await send_help(bot, chat_id, s)
            except Exception as e:
                log.error("Action %s error: %s", text, e)
                await event.reply(f"Thao tác thất bại: {e}")
            return

        if text == "Xem hóa đơn":
            await flows.handle_show_invoice(bot, event, s)
            return
        if text == "Tạo HD":
            if not config.is_admin(uid):
                await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
                return
            s.confirm_kv = {"active": True}
            await event.reply(
                "Bạn có chắc chắn tạo hóa đơn Kiotviet cho đơn hàng này không?",
                buttons=keyboards.build_kv_confirm_keyboard(),
            )
            return
        if text == "In hóa đơn giao":
            await flows.handle_get_html(bot, event, s)
            return
        if text == "Xem thông tin":
            await flows.handle_view_info(bot, event, s)
            return
        if text == "Xem khách hàng":
            await flows.handle_view_customer(bot, event, s)
            return
        if text == "Sửa tên đơn hàng":
            if not config.is_admin(uid):
                await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
                return
            s.awaiting_rename = True
            await event.reply(
                "Hãy gửi tên đơn hàng mới (văn bản).",
                buttons=keyboards.build_rename_keyboard(),
            )
            return
        if text == "Hối":
            if not s.thread_id:
                await event.reply("Không lấy được thread_id.")
                return
            try:
                await post_json(f"{ORDER_API_BASE}/api/order/reply", {"thread_id": s.thread_id, "text": "Hối", "times": 2})
                await event.reply("Đã hối đơn hàng.")
            except Exception as e:
                log.error("Hoi error: %s", e)
                await event.reply(f"Hối thất bại: {e}")
            return

        # Delegate to active flow handlers
        if s.edit_invoice and s.edit_invoice.get("active"):
            await flows.handle_invoice_edit_text(bot, event, s, text)
            return
        if s.confirm_kv and s.confirm_kv.get("active"):
            await flows.handle_kv_confirm_text(bot, event, s, text)
            return
        if s.pay_flow and s.pay_flow.get("active"):
            await flows.handle_payment_text(bot, event, s, text)
            return
        if s.nop_wizard and s.nop_wizard.get("active"):
            await flows.handle_nop_wizard_text(bot, event, s, text)
            return
        if s.confirm_print and s.confirm_print.get("active"):
            await flows.handle_confirm_print_text(bot, event, s, text)
            return
        if s.awaiting_rename:
            await flows.handle_rename_text(bot, event, s, text)
            return

    # Search pagination callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^s:\d+$")))
    async def on_search_page(event):
        page = int(event.data.decode().split(":")[1])
        keyword = _search_state.get(event.chat_id, "")
        if not keyword:
            await event.answer("Hết hạn tìm kiếm. Dùng /s <keyword> để tìm lại.", alert=True)
            return
        _search_page[event.chat_id] = page
        await _send_search_page(bot, event, page, keyword, edit=True)

    # List pagination callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:page:\d+$")))
    async def on_list_page(event):
        page = int(event.data.decode().split(":")[2])
        await _send_list_page(bot, event, event.chat_id, page=page, edit=True)

    # List reload callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:reload$")))
    async def on_list_reload(event):
        page = _list_state.get(event.chat_id, 1)
        try:
            await event.delete()
        except Exception:
            pass
        await _send_list_page(bot, event, event.chat_id, page=page, edit=False)

    # Search order detail callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:order:\d+$")))
    async def on_search_order(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        thread_id = int(event.data.decode().split(":")[2])
        await _send_order_detail(bot, event, thread_id, list_page=None)
        await event.answer()

    # Search back-to-results callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:back:\d+$")))
    async def on_search_back(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        keyword = _search_state.get(event.chat_id, "")
        if not keyword:
            await event.answer("Hết hạn tìm kiếm. Dùng /s <keyword> để tìm lại.", alert=True)
            return
        page = int(event.data.decode().split(":")[2])
        _search_page[event.chat_id] = page
        await _send_search_page(bot, event, page, keyword, edit=True)

    # Search noop callback (page indicator button)
    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:noop$")))
    async def on_search_noop(event):
        await event.answer()

    # List noop callback (page indicator button)
    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:noop$")))
    async def on_list_noop(event):
        await event.answer()

    # List order detail callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:order:\d+$")))
    async def on_list_order(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        thread_id = int(event.data.decode().split(":")[2])
        page = _list_state.get(event.chat_id, 1)
        await _send_order_detail(bot, event, thread_id, list_page=page)
        await event.answer()

    # List back-to-list callback
    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:back:\d+$")))
    async def on_list_back(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        page = int(event.data.decode().split(":")[2])
        await _send_list_page(bot, event, event.chat_id, page=page, edit=True)


def register_all(bot):
    """Register all handlers on a bot client."""
    register_start(bot)
    register_steps(bot)
    register_show_invoice(bot)
    register_reply_actions(bot)
    register_sheet_commands(bot)
    register_media_handlers(bot)
    register_callbacks(bot)
