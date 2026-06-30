"""bot_handlers/chua_nop.py — Chưa nộp tiền page view."""
import logging

from telethon import Button

from bot_core import db

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

        buttons = []
        labels = []
        for o in orders:
            tid = o.get("thread_id")
            text_raw = (o.get("text") or "").replace("\n", " ").strip()
            created_raw = (o.get("created") or "").strip()
            ddmm = created_raw[8:10] + "/" + created_raw[5:7] if len(created_raw) >= 10 else ""
            ts = o.get("task_status") or {}
            def icon(task_name):
                st = ts.get(task_name) or {}
                if st.get("done"):
                    return "✅"
                if task_name == "nop_tien" and str(st.get("note", "")).lower() == "chieu_lay_tien":
                    return "🟡"
                return "❌"
            status = "".join(icon(k) for k in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"))
            if tid:
                label = f"{status} {ddmm} {text_raw}" if ddmm else f"{status} {text_raw}"
                labels.append((tid, label))

        if labels:
            max_w = max(len(l) for _, l in labels)
            for tid, label in labels:
                pad = " ." * ((max_w - len(label) + 1) // 2) if len(label) < max_w else ""
                buttons.append([Button.inline(label + pad, f"list:order:{tid}".encode())])

        total_pages = (total + 9) // 10
        nav = []
        if page > 1:
            nav.append(Button.inline("◀ Trước", f"chuanop:{page - 1}".encode()))
        nav.append(Button.inline(f"📄 {page}/{total_pages}", b"chuanop:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau ▶", f"chuanop:{page + 1}".encode()))
        if nav:
            buttons.append(nav)

        header = f"📋 Đã giao chưa nộp/nhận — {total} đơn — Trang {page}/{total_pages}"
        if edit:
            await event.edit(header, buttons=buttons, link_preview=False)
        else:
            await event.reply(header, buttons=buttons, link_preview=False)
    except Exception as e:
        log.error("chua_nop error: %s", e)
        await event.reply(f"❌ Không thể tải danh sách: {e}")


async def _send_chua_nop_table(bot, event, page=1, edit=False):
    """Send /chua_nop data as a text table in a code block."""
    try:
        orders, total = db.get_orders_without_nop(page=page, per_page=10)
        if not orders:
            text = "Không tìm thấy đơn hàng chưa nộp/nhận."
            if edit:
                await event.edit(text)
            else:
                await event.reply(text)
            return

        lines = ["bh sh gh nt nh ng\u00e0y  n\u1ed9i dung"]
        for o in orders:
            text_raw = (o.get("text") or "").replace("\n", " ").strip()
            created_raw = (o.get("created") or "").strip()
            ddmm = created_raw[8:10] + "/" + created_raw[5:7] if len(created_raw) >= 10 else ""
            ts = o.get("task_status") or {}
            def icon(task_name):
                st = ts.get(task_name) or {}
                if st.get("done"):
                    return "\u2705"
                if task_name == "nop_tien" and str(st.get("note", "")).lower() == "chieu_lay_tien":
                    return "\U0001f7e1"
                return "\u274c"
            status = " ".join(icon(k) for k in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"))
            line = f"{status} {ddmm}  {text_raw}"
            lines.append(line)

        total_pages = (total + 9) // 10
        table = "```\n" + "\n".join(lines) + "\n```"
        footer = f"\U0001f4cb \u0110\u00e3 giao ch\u01b0a n\u1ed9p/nh\u1eadn \u2014 {total} \u0111\u01a1n \u2014 Trang {page}/{total_pages}"

        nav = []
        if page > 1:
            nav.append(Button.inline("\u25c0 Tr\u01b0\u1edbc", f"chuanopt:{page - 1}".encode()))
        nav.append(Button.inline(f"\U0001f4c4 {page}/{total_pages}", b"chuanopt:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau \u25b6", f"chuanopt:{page + 1}".encode()))

        text = table + "\n\n" + footer
        if edit:
            await event.edit(text, buttons=nav if nav else None, link_preview=False)
        else:
            await event.reply(text, buttons=nav if nav else None, link_preview=False)
    except Exception as e:
        log.error("chua_nop table error: %s", e)
        await event.reply(f"\u274c Kh\u00f4ng th\u1ec3 t\u1ea3i danh s\u00e1ch: {e}")
