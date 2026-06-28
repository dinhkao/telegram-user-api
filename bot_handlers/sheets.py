"""bot_don_hang/handlers/sheets.py — Google Sheets commands (/chua_soan etc)."""
import json
import logging
import re

from telethon import events

from bot_core import config
from bot_core.utils import esc_html, mark_once
from .search_list import _send_chua_nop_page

log = logging.getLogger("bot.handlers")

CHUA_SOAN_SHEET_ID = "1uxAFE9SFN98RI25_AE0LN-IADxcx5rz0wnh9cEHP_VQ"
CHUA_SOAN_SHEET_GID = 0
CHUA_SOAN_PRIVATE_CHANNEL_ID = "2138495144"


def _parse_gviz_response(text):
    match = re.search(r'google\.visualization\.Query\.setResponse\(([\s\S]*?)\);?\s*$', text)
    if not match:
        raise ValueError("Không đọc được dữ liệu Google Sheets.")
    return json.loads(match.group(1))


def _find_private_post_anchor(text):
    match = re.search(r'<a\s+href=["\'](tg://privatepost\?[^"\']+)["\'][^>]*>([\s\S]*?)</a>', text)
    if not match:
        return None
    return {"link": match.group(1), "text": match.group(2)}


def _parse_order_cell(raw, required_tag=None, excluded_tag=None):
    normalized = str(raw or "").replace('""', '"')
    if not normalized.strip():
        return None
    if required_tag and required_tag not in normalized:
        return None
    if excluded_tag and excluded_tag in normalized:
        return None
    before_block = normalized.split('<blockquote')[0] or ""
    anchor = _find_private_post_anchor(before_block)
    if not anchor:
        block_match = re.search(r'<blockquote[^>]*>([\s\S]*?)</blockquote>', normalized, re.I)
        if block_match:
            anchor = _find_private_post_anchor(block_match.group(1))
    if not anchor:
        matches = list(re.finditer(r'<a\s+href=["\'](tg://privatepost\?[^"\']+)["\'][^>]*>([\s\S]*?)</a>', normalized))
        if matches:
            anchor = {"link": matches[-1].group(1), "text": matches[-1].group(2)}
    if not anchor:
        return None
    text = re.sub(r'<[^>]*>', '', str(anchor.get("text") or "")).replace(r'\s+', ' ').strip()
    if not text:
        return None
    return {"text": text}


async def _fetch_orders_by_tag(required_tag=None, excluded_tag=None):
    import aiohttp
    url = f"https://docs.google.com/spreadsheets/d/{CHUA_SOAN_SHEET_ID}/gviz/tq?gid={CHUA_SOAN_SHEET_GID}&tqx=out:json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
    data = _parse_gviz_response(text)
    rows = (data.get("table") or {}).get("rows", [])
    orders = []
    for row in rows:
        cells = row.get("c", [])
        id_cell = cells[0] if len(cells) > 0 else None
        raw_id = id_cell.get("v") if id_cell else None
        message_id = str(raw_id or "").replace(r"[^0-9]", "").strip()
        cell = cells[1] if len(cells) > 1 else None
        raw = cell.get("v") if cell else None
        if not raw or not message_id:
            continue
        parsed = _parse_order_cell(raw, required_tag, excluded_tag)
        if parsed:
            orders.append({
                "text": parsed["text"],
                "link": f"tg://privatepost?channel={CHUA_SOAN_PRIVATE_CHANNEL_ID}&post={message_id}",
            })
    return orders


def _chunk_lines(lines, max_len=3800):
    chunks = []
    current = ""
    for line in lines:
        piece = str(line)
        if not current:
            current = piece
            continue
        candidate = f"{current}\n\n{piece}"
        if len(candidate) > max_len:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def _reply_orders_by_tag(event, tag, excluded=None):
    try:
        orders = await _fetch_orders_by_tag(tag, excluded)
        if not orders:
            await event.reply("Không tìm thấy đơn hàng trong cột B.")
            return
        lines = [f'<a href="{esc_html(o["link"])}">{esc_html(o["text"])}</a>' for o in orders]
        chunks = _chunk_lines(lines)
        for chunk in chunks:
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
