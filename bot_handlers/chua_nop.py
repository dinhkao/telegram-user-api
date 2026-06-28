"""bot_handlers/chua_nop.py — Chưa nộp tiền page view."""
import logging

from telethon import Button

from bot_core import config, db

log = logging.getLogger("bot.handlers")


async def _send_chua_nop_page(bot, event, page=1, edit=False):
    """Orders where nop_tien OR nhan_tien is NOT done."""
    try:
        orders, total = db.get_orders_without_nop(page=page, per_page=10)
        if not orders:
            text = "Không tìm thấy đơn hàng chưa nộp/nhận."
            if edit:
                await event.edit(text, buttons=None)
            else:
                await event.reply(text)
            return

        base = str(config.GROUP_CHAT_ID).replace("-100", "")
        icons_map = {"nop_tien": "💸", "nhan_tien": "💰"}
        buttons = []
        for o in orders:
            tid = o.get("thread_id")
            name = o.get("text", "")[:50]
            ts = o.get("task_status") or {}
            status = "".join(
                icons_map[k] + ("✅" if (ts.get(k) or {}).get("done") else "❌")
                for k in ("nop_tien", "nhan_tien")
            )
            if tid:
                buttons.append([Button.inline(f"{status} {name}", f"list:order:{tid}".encode())])

        total_pages = (total + 9) // 10
        nav = []
        if page > 1:
            nav.append(Button.inline("◀ Trước", f"chuanop:{page - 1}".encode()))
        nav.append(Button.inline(f"📄 {page}/{total_pages}", b"chuanop:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau ▶", f"chuanop:{page + 1}".encode()))
        if nav:
            buttons.append(nav)

        header = f"📋 Đơn chưa nộp/nhận — {total} đơn — Trang {page}/{total_pages}"
        if edit:
            await event.edit(header, buttons=buttons, link_preview=False)
        else:
            await event.reply(header, buttons=buttons, link_preview=False)
    except Exception as e:
        log.error("chua_nop error: %s", e)
        await event.reply(f"❌ Không thể tải danh sách: {e}")
