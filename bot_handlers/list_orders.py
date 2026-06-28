"""bot_handlers/list_orders.py — List & order detail views."""
import logging
from telethon import Button
from bot_core import config, db
from bot_core.utils import esc_html

log = logging.getLogger("bot.handlers")
_list_state: dict[int, int] = {}

async def _send_list_page(bot, event, chat_id, page=1, edit=False):
    try:
        orders, total = db.get_orders_without_giao_paginated(page=page, per_page=10, days=30)
        if not orders:
            msg = "Không tìm thấy đơn hàng chưa giao trong 30 ngày qua."
            if edit:
                await event.edit(msg, buttons=None, link_preview=False)
            else:
                await event.reply(msg)
            return
        _list_state[chat_id] = page
        total_pages = (total + 9) // 10
        buttons = []
        for o in orders:
            tid = o.get("thread_id")
            name = (o.get("text", "") or f"Đơn #{tid}")[:50]
            if tid:
                buttons.append([Button.inline(name, f"list:order:{tid}".encode())])
        nav = []
        if page > 1:
            nav.append(Button.inline("◀ Trước", f"list:page:{page - 1}".encode()))
        nav.append(Button.inline(f"📄 {page}/{total_pages}", b"list:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau ▶", f"list:page:{page + 1}".encode()))
        if nav:
            buttons.append(nav)
        buttons.append([Button.inline("🔄 Tải lại", b"list:reload")])
        header = f"📦 Đơn chưa giao (30 ngày) — {total} đơn — Trang {page}/{total_pages}"
        if edit:
            await event.edit(header, buttons=buttons, link_preview=False)
        else:
            await event.reply(header, buttons=buttons, link_preview=False)
    except Exception as e:
        log.error("list page error: %s", e)
        await event.reply(f"Không thể tải danh sách: {e}")

async def _send_order_detail(bot, event, thread_id: int, list_page: int | None = None):
    try:
        order = db.get_order_by_thread(int(thread_id))
        if not order:
            await event.reply("Không tìm thấy đơn hàng.")
            return
        text = order.get("text", "") or ""
        ts = order.get("task_status") or {}
        customer = order.get("kh") or order.get("customerNameOverride") or ""
        base = str(config.GROUP_CHAT_ID).replace("-100", "")
        url = f"tg://privatepost?channel={base}&post={thread_id}"
        lines = [f'📄 <a href="{url}"><b>Đơn #{thread_id}</b></a> — {esc_html(customer)}', ""]
        first_line = text.split("\n")[0] if text else ""
        if first_line:
            lines.append(f"📝 {esc_html(first_line)}")
            lines.append("")
        task_icons = {"ban_hd": "🛒 Bán", "soan_hang": "📋 Soạn", "giao_hang": "🚚 Giao",
            "nop_tien": "💸 Nộp", "nhan_tien": "💵 Nhận"}
        has_tasks = any(ts.get(k) for k in task_icons)
        if has_tasks:
            lines.append("<b>Tiến độ:</b>")
            for key, label in task_icons.items():
                st = ts.get(key) or {}
                if not st:
                    continue
                note = st.get("note", "") or ""
                note_str = f" ({esc_html(str(note))})" if note else ""
                icon = "🔘" if st.get("skip") else "✅" if st.get("done") else "❌"
                lines.append(f"  {icon} {label}{note_str}")
        lines.append("")
        from .search_list import _search_page
        if list_page is not None:
            back_data = f"list:back:{list_page}".encode()
            back_label = "◀ Quay lại danh sách"
        else:
            sp = _search_page.get(event.chat_id, 1)
            back_data = f"search:back:{sp}".encode()
            back_label = "◀ Quay lại tìm kiếm"
        await event.reply("\n".join(lines), buttons=[[Button.inline(back_label, back_data)]],
            parse_mode="html", link_preview=False)
    except Exception as e:
        log.error("order detail error: %s", e)
        await event.reply(f"❌ Lỗi tải chi tiết đơn: {e}")
