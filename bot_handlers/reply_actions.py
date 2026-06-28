"""bot_handlers/reply_actions.py — Reply keyboard actions router."""
import logging
from telethon import events
from telethon.tl.types import MessageService
from bot_core import config, store
from bot_core.utils import mark_once
from .search_list import _send_list_page, _send_search_page, _search_state, _search_page
from .action_handlers import handle_action
from .menu_handler import handle_menu
from .callbacks_nav import register_nav_callbacks

log = logging.getLogger("bot.handlers")

def register_show_invoice(bot):
    @bot.on(events.NewMessage(pattern=r"^/show_invoice(?:\s+(\S+))?"))
    async def h(event):
        if not mark_once(event):
            return
        if not config.is_allowed(event.sender_id):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        s = store.get(event.chat_id)
        order_id = (event.pattern_match.group(1) or "").strip() or (s.order_id if s else None)
        if not order_id or not s or order_id != s.order_id:
            await event.reply("Vui lòng bắt đầu bằng liên kết đơn hàng.")
            return
        import bot_flows as flows
        await flows.handle_show_invoice(bot, event, s)

def register_reply_actions(bot):
    @bot.on(events.NewMessage)
    async def h(event):
        if isinstance(event.message, MessageService):
            return
        text = (event.message.text or "").strip()
        chat_id, uid = event.chat_id, event.sender_id
        if not config.is_allowed(uid):
            return
        if text.strip().lower() == "list":
            if not mark_once(event):
                return
            await _send_list_page(bot, event, chat_id, page=1)
            return
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
        if await handle_action(bot, event, s, text, uid):
            return
        await handle_menu(bot, event, s, text, uid)

def register_all(bot):
    from .start_steps import register_start, register_steps
    from .sheets import register_sheet_commands
    from .media_events import register_media_handlers
    from .callbacks import register_callbacks
    register_start(bot)
    register_steps(bot)
    register_show_invoice(bot)
    register_reply_actions(bot)
    register_nav_callbacks(bot)
    register_sheet_commands(bot)
    register_media_handlers(bot)
    register_callbacks(bot)
