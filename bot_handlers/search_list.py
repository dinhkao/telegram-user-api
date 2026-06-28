"""bot_don_hang/handlers/search_list.py — Paged search + list of orders."""
import logging

from telethon import Button

from bot_core import config, db
from bot_core.utils import esc_html

log = logging.getLogger("bot.handlers")

# Module-level state for paging callback handlers
_search_state: dict[int, str] = {}
_list_state: dict[int, int] = {}  # chat_id -> current page for list command


async def _send_search_page(bot, event, page: int, keyword: str, edit: bool = False):
    """Render one page of search results with inline buttons (like list)."""
    try:
        orders, total = db.search_orders(keyword, page=page, per_page=10)
        if not orders:
            if edit:
                await event.edit("Không tìm thấy đơn hàng nào.", buttons=None)
            else:
                await event.reply("Không tìm thấy đơn hàng nào.")
            return

        _search_state[event.chat_id] = keyword
        total_pages = (total + 9) // 10
        buttons = []

        for o in orders:
            tid = o.get("thread_id")
            name = o.get("text", "") or f"Đơn #{tid}"
            if len(name) > 50:
                name = name[:47] + "..."

            # Status icons (compact)
            ts = o.get("task_status") or {}
            icons = []
            for tt in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"):
                st = ts.get(tt) or {}
                if tt == "nhan_tien" and st.get("done") and str(st.get("note", "")).lower() == "gtr":
                    icons.append("📄")
                elif tt == "nop_tien" and not st.get("done") and str(st.get("note", "")).lower() == "chieu_lay_tien":
                    icons.append("🟨")
                elif st.get("done"):
                    icons.append("🔘" if st.get("skip") else "✅")
                else:
                    icons.append("❌")
            nhan_done = (ts.get("nhan_tien") or {}).get("done")
            icons.append("💰" if nhan_done else "😠")
            status = "".join(icons)

            # Date
            date_str = ""
            created = o.get("created", "")
            if created:
                try:
                    raw = created.strip()
                    if "T" in raw:
                        raw = raw.split("T")[0]
                    elif " " in raw:
                        raw = raw.split(" ")[0]
                    parts = raw.split("-")
                    if len(parts) >= 3:
                        date_str = f"{parts[2]}/{parts[1]}"
                except Exception:
                    pass

            label = f"{date_str} {status} {name}" if date_str else f"{status} {name}"
            if tid:
                buttons.append([Button.inline(label, f"search:order:{tid}".encode())])

        # Navigation row
        nav = []
        if page > 1:
            nav.append(Button.inline("◀ Trước", f"s:{page - 1}".encode()))
        nav.append(Button.inline(f"📄 {page}/{total_pages}", b"search:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau ▶", f"s:{page + 1}".encode()))
        if nav:
            buttons.append(nav)

        header = f'🔍 "{esc_html(keyword)}" — {total} kết quả — Trang {page}/{total_pages}'
        if edit:
            await event.edit(header, buttons=buttons, link_preview=False)
        else:
            await event.reply(header, buttons=buttons, link_preview=False)
    except Exception as e:
        log.error("search error: %s", e, exc_info=True)
        if edit:
            await event.edit(f"❌ Lỗi: {e}", buttons=None)
        else:
            await event.reply(f"❌ Lỗi: {e}")


async def _send_list_page(bot, event, chat_id, page=1, edit=False):
    """Render one page of orders without giao_hang with inline nav + reload."""
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
            name = o.get("text", "") or f"Đơn #{tid}"
            if len(name) > 50:
                name = name[:47] + "..."
            if tid:
                buttons.append([Button.inline(name, f"list:order:{tid}".encode())])

        # Navigation row
        nav = []
        if page > 1:
            nav.append(Button.inline("◀ Trước", f"list:page:{page - 1}".encode()))
        nav.append(Button.inline(f"📄 {page}/{total_pages}", b"list:noop"))
        if page < total_pages:
            nav.append(Button.inline("Sau ▶", f"list:page:{page + 1}".encode()))
        if nav:
            buttons.append(nav)

        # Reload button
        buttons.append([Button.inline("🔄 Tải lại", b"list:reload")])

        header = f"📦 Đơn chưa giao (30 ngày) — {total} đơn — Trang {page}/{total_pages}"
        if edit:
            await event.edit(header, buttons=buttons, link_preview=False)
        else:
            await event.reply(header, buttons=buttons, link_preview=False)
    except Exception as e:
        log.error("list page error: %s", e)
        if edit:
            await event.edit(f"Không thể tải danh sách: {e}", buttons=None)
        else:
            await event.reply(f"Không thể tải danh sách: {e}")


async def _send_order_detail(bot, event, thread_id: int, list_page: int | None = None):
    """Fetch an order by thread_id and send its data to the chat, with a link to it."""
    try:
        order = db.get_order_by_thread(int(thread_id))
        if not order:
            await event.reply("Không tìm thấy đơn hàng.")
            return

        text = order.get("text", "") or ""
        ts = order.get("task_status") or {}
        customer = order.get("kh") or order.get("customerNameOverride") or ""
        invoice = order.get("invoice") or []
        discount = int(order.get("discount", 0) or 0)

        # ── Header: customer + invoice link ──
        base = str(config.GROUP_CHAT_ID).replace("-100", "")
        url = f"tg://privatepost?channel={base}&post={thread_id}"
        header_parts = [f'📄 <a href="{url}"><b>Đơn #{thread_id}</b></a>']
        if customer:
            header_parts.append(f"🧑 {esc_html(customer)}")
        header = " — ".join(header_parts)
        lines = [header, ""]

        # ── Raw message text (first line as summary) ──
        first_line = text.split("\n")[0] if text else ""
        if first_line:
            lines.append(f"📝 {esc_html(first_line)}")
            lines.append("")

        # ── Invoice rows ──
        labels = [
            ("bản vẽ", "📐"),
            ("soi", "🔬"),
            ("ép", "⚡"),
            ("gá", "🔧"),
            ("số lượng", "📦"),
            ("phôi", "🧱"),
            ("mài", "🪨"),
        ]
        invoice_total = 0
        for key, icon in labels:
            val = None
            for inv in invoice:
                v = inv.get(key) or inv.get(key.replace(" ", "_")) or None
                if v:
                    val = v
                    break
            if val is not None:
                try:
                    num = int(val)
                    invoice_total += num
                    lines.append(f"  {icon} {key}: <b>{num:,}</b>")
                except (ValueError, TypeError):
                    lines.append(f"  {icon} {key}: {esc_html(str(val))}")

        pvc = order.get("pvc") or 0
        vat = int(order.get("vat", 0) or 0)
        kh_debt = order.get("kh_debt") or 0
        total_payments = order.get("total_payments", 0) or 0

        if invoice_total or discount or pvc or vat or kh_debt or total_payments:
            lines.append("")
            if invoice_total:
                lines.append(f"  💵 Tổng: <b>{invoice_total:,}</b>")
            if discount:
                lines.append(f"  🏷 Giảm: <b>{discount:,}</b>")
            if pvc:
                lines.append(f"  🧾 PVC: <b>{pvc:,}</b>")
            if vat:
                lines.append(f"  📊 VAT: <b>{vat}%</b>")
            if kh_debt:
                lines.append(f"  💳 KH nợ: <b>{kh_debt:,}</b>")
            if total_payments:
                lines.append(f"  💰 Đã thanh toán: <b>{total_payments:,}</b>")

        # ── Task status ──
        task_icons = {
            "ban_hd": "🛒 Bán",
            "soan_hang": "📋 Soạn",
            "giao_hang": "🚚 Giao",
            "nop_tien": "💸 Nộp",
            "nhan_tien": "💵 Nhận",
        }
        has_tasks = any(ts.get(k) for k in task_icons)
        if has_tasks:
            lines.append("")
            lines.append("<b>Tiến độ:</b>")
            for key, label in task_icons.items():
                st = ts.get(key) or {}
                if not st:
                    continue
                note = st.get("note", "") or ""
                note_str = f" ({esc_html(str(note))})" if note else ""
                if st.get("done"):
                    icon = "🔘" if st.get("skip") else "✅"
                    lines.append(f"  {icon} {label}{note_str}")
                else:
                    lines.append(f"  ❌ {label}{note_str}")

        lines.append("")
        text_reply = "\n".join(lines)

        # Build back button
        if list_page is not None:
            back_data = f"list:back:{list_page}".encode()
            back_label = "◀ Quay lại danh sách"
        else:
            # Search — look up current page from _search_state; fall back to page 1
            sp = _search_page.get(event.chat_id, 1)
            back_data = f"search:back:{sp}".encode()
            back_label = "◀ Quay lại tìm kiếm"

        buttons = [[Button.inline(back_label, back_data)]]
        await event.reply(text_reply, buttons=buttons, parse_mode="html", link_preview=False)
    except Exception as e:
        log.error("order detail error: %s", e, exc_info=True)
        await event.reply(f"❌ Lỗi tải chi tiết đơn: {e}")


# Store the current search page per chat so back navigation works
_search_page: dict[int, int] = {}


async def _send_chua_nop_page(bot, event, page=1, edit=False):
    """Orders where nop_tien OR nhan_tien is NOT done, created after 2026-04-01."""
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
            label = f"{status} {name}"
            if tid:
                buttons.append([Button.inline(label, f"list:order:{tid}".encode())])

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
        log.error("chua_nop error: %s", e, exc_info=True)
        if edit:
            await event.edit(f"❌ Lỗi: {e}", buttons=None)
        else:
            await event.reply(f"❌ Không thể tải danh sách: {e}")
