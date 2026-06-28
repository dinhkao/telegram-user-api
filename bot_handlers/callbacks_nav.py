"""bot_handlers/callbacks_nav.py — Search & list pagination callbacks."""
import re

from telethon import events

from bot_core import config
from .search_list import _send_search_page, _send_list_page, _send_order_detail
from .search_list import _search_state, _search_page, _list_state


def register_nav_callbacks(bot):
    """Register search/list pagination callback handlers."""

    @bot.on(events.CallbackQuery(data=re.compile(rb"^s:\d+$")))
    async def on_search_page(event):
        page = int(event.data.decode().split(":")[1])
        keyword = _search_state.get(event.chat_id, "")
        if not keyword:
            await event.answer("Hết hạn tìm kiếm.", alert=True)
            return
        _search_page[event.chat_id] = page
        await _send_search_page(bot, event, page, keyword, edit=True)

    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:page:\d+$")))
    async def on_list_page(event):
        page = int(event.data.decode().split(":")[2])
        await _send_list_page(bot, event, event.chat_id, page=page, edit=True)

    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:reload$")))
    async def on_list_reload(event):
        page = _list_state.get(event.chat_id, 1)
        try:
            await event.delete()
        except Exception:
            pass
        await _send_list_page(bot, event, event.chat_id, page=page, edit=False)

    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:order:\d+$")))
    async def on_search_order(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        thread_id = int(event.data.decode().split(":")[2])
        await _send_order_detail(bot, event, thread_id, list_page=None)
        await event.answer()

    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:back:\d+$")))
    async def on_search_back(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        keyword = _search_state.get(event.chat_id, "")
        if not keyword:
            await event.answer("Hết hạn tìm kiếm.", alert=True)
            return
        page = int(event.data.decode().split(":")[2])
        _search_page[event.chat_id] = page
        await _send_search_page(bot, event, page, keyword, edit=True)

    @bot.on(events.CallbackQuery(data=re.compile(rb"^search:noop$")))
    async def on_search_noop(event):
        await event.answer()

    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:noop$")))
    async def on_list_noop(event):
        await event.answer()

    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:order:\d+$")))
    async def on_list_order(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        thread_id = int(event.data.decode().split(":")[2])
        page = _list_state.get(event.chat_id, 1)
        await _send_order_detail(bot, event, thread_id, list_page=page)
        await event.answer()

    @bot.on(events.CallbackQuery(data=re.compile(rb"^list:back:\d+$")))
    async def on_list_back(event):
        if not config.is_allowed(event.sender_id):
            await event.answer("Không có quyền.", alert=True)
            return
        page = int(event.data.decode().split(":")[2])
        await _send_list_page(bot, event, event.chat_id, page=page, edit=True)
