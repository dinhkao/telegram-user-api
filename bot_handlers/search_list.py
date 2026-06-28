"""bot_handlers/search_list.py — Paged search of orders."""
import logging

from telethon import Button

from bot_core import config, db
from bot_core.utils import esc_html

log = logging.getLogger("bot.handlers")

MAX_CACHE = 500

_search_state: dict[int, str] = {}
_search_page: dict[int, int] = {}

def _cleanup_cache(cache: dict, maxsize: int = MAX_CACHE):
    if len(cache) > maxsize:
        keys = list(cache.keys())[:len(cache) - maxsize]
        for k in keys:
            del cache[k]


async def _send_search_page(bot, event, page: int, keyword: str, edit: bool = False):
    """Render one page of search results with inline buttons."""
    try:
        orders, total = db.search_orders(keyword, page=page, per_page=10)
        if not orders:
            if edit:
                await event.edit("Không tìm thấy đơn hàng nào.", buttons=None)
            else:
                await event.reply("Không tìm thấy đơn hàng nào.")
            return

        _cleanup_cache(_search_state)
        _cleanup_cache(_search_page)
        _search_state[event.chat_id] = keyword
        total_pages = (total + 9) // 10
        buttons = []

        for o in orders:
            tid = o.get("thread_id")
            name = o.get("text", "") or f"Đơn #{tid}"
            if len(name) > 50:
                name = name[:47] + "..."

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

            date_str = ""
            created = o.get("created", "")
            if created:
                try:
                    raw = created.strip().split("T")[0].split(" ")[0]
                    parts = raw.split("-")
                    if len(parts) >= 3:
                        date_str = f"{parts[2]}/{parts[1]}"
                except Exception:
                    pass

            label = f"{date_str} {''.join(icons)} {name}" if date_str else f"{''.join(icons)} {name}"
            if tid:
                buttons.append([Button.inline(label, f"search:order:{tid}".encode())])

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
        log.error("search error: %s", e)
        await event.reply(f"❌ Lỗi: {e}")


# Re-export from split files
from bot_handlers.list_orders import _send_list_page, _send_order_detail, _list_state
from bot_handlers.chua_nop import _send_chua_nop_page
