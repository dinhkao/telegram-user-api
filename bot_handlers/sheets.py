"""bot_handlers/sheets.py — Google Sheets commands (/chua_soan etc)."""
import logging
import re

from telethon import events

from bot_core import config
from bot_core.utils import esc_html, mark_once
from .sheets_helpers import fetch_orders_by_tag, chunk_lines
from .chua_nop import _send_chua_nop_page

log = logging.getLogger("bot.handlers")

CHUA_SOAN_SHEET_ID = "1uxAFE9SFN98RI25_AE0LN-IADxcx5rz0wnh9cEHP_VQ"
CHUA_SOAN_SHEET_GID = 0
CHUA_SOAN_PRIVATE_CHANNEL_ID = "2138495144"


async def _reply_orders_by_tag(event, tag, excluded=None):
    try:
        orders = await fetch_orders_by_tag(
            CHUA_SOAN_SHEET_ID, CHUA_SOAN_SHEET_GID, CHUA_SOAN_PRIVATE_CHANNEL_ID, tag, excluded
        )
        if not orders:
            await event.reply("Không tìm thấy đơn hàng trong cột B.")
            return
        lines = [f'<a href="{esc_html(o["link"])}">{esc_html(o["text"])}</a>' for o in orders]
        for chunk in chunk_lines(lines):
            await event.reply(chunk, parse_mode="html", link_preview=False)
    except Exception as e:
        log.error("sheets tag %s error: %s", tag, e)
        await event.reply(f"Không thể tải danh sách: {e}")


def register_sheet_commands(bot):
    @bot.on(events.NewMessage(pattern=r"^/chua_soan\b"))
    async def h(event):
        if not mark_once(event):
            return
        if not config.is_allowed(event.sender_id):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        await _reply_orders_by_tag(event, "#chua_soan")

    @bot.on(events.NewMessage(pattern=r"^/chua_giao\b"))
    async def h(event):
        if not mark_once(event):
            return
        if not config.is_allowed(event.sender_id):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        await _reply_orders_by_tag(event, "#chua_giao")

    @bot.on(events.NewMessage(pattern=r"^/chua_nop_tien\b"))
    async def h(event):
        if not mark_once(event):
            return
        if not config.is_allowed(event.sender_id):
            await event.reply("Xin lỗi, bot này chỉ dành cho nhân viên được cấp quyền.")
            return
        await _reply_orders_by_tag(event, "#chua_nop_tien", "#chua_giao")

    @bot.on(events.NewMessage(pattern=r"^/chua_nop\b"))
    async def h(event):
        if not mark_once(event):
            return
        if not config.is_allowed(event.sender_id):
            return
        await _send_chua_nop_page(bot, event, 1)

    @bot.on(events.CallbackQuery(data=re.compile(rb"^chuanop:\d+$")))
    async def on_chua_nop_page(event):
        page = int(event.data.decode().split(":")[1])
        await _send_chua_nop_page(bot, event, page, edit=True)
