"""bot_don_hang/handlers/session.py — Session lifecycle & help reply keyboard."""
import logging

from telethon import Button

from bot_core import config, db, keyboards, store
from bot_core.utils import esc_html, name_of_user_id

log = logging.getLogger("bot.handlers")
GROUP_CHAT_ID = config.GROUP_CHAT_ID


async def clear_session(chat_id: int, silent: bool = False, bot=None):
    s = store.get(chat_id)
    if not s:
        return
    if s.timer:
        s.timer.cancel()
    store.delete(chat_id)
    if not silent:
        try:
            if bot is None:
                from bot_core.main import get_bot
                bot = get_bot()
            if bot is not None:
                await bot.send_message(chat_id, "Phiên làm việc đã kết thúc do 1 phút không tương tác.", buttons=Button.clear())
            else:
                log.warning("clear_session: bot is None")
        except Exception as e:
            log.warning("clear_session send failed: %s", e)


async def _fire_and_forget_delete(bot, chat_id: int, msg_id: int):
    """Delete a message without blocking the caller."""
    try:
        await bot.delete_messages(chat_id, [msg_id])
    except Exception:
        pass


async def send_help(bot, chat_id: int, s: store.Session, caption: str = ""):
    name = esc_html(s.last_text or "")
    msg = f"Bạn đang thao tác với đơn hàng\n<code>{name}</code>\nChọn thao tác muốn thực hiện." if name else "Chọn thao tác muốn thực hiện."
    if caption:
        msg = f"{caption}\n\n{msg}"
    if s.thread_id and not s.sent_initial:
        channel = str(GROUP_CHAT_ID).replace("-100", "")
        url = f"tg://privatepost?channel={channel}&post={s.thread_id}"
        msg += f'\n<a href="{esc_html(url)}">Đi đến group chat của đơn hàng này</a>'
    kb = keyboards.build_actions_keyboard(s.task_status, s.user_id)

    old_id = s.last_list_msg_id
    m = await bot.send_message(chat_id, msg, parse_mode="html", buttons=kb, link_preview=False)
    s.last_list_msg_id = m.id

    if old_id:
        import asyncio
        asyncio.create_task(_fire_and_forget_delete(bot, chat_id, old_id))


async def start_session(bot, chat_id: int, order_id: str, user_id: int):
    await clear_session(chat_id, silent=True)
    s = store.Session(chat_id=chat_id, order_id=order_id, user_id=user_id)
    store.set_(chat_id, s)

    order = db.get_order(order_id)
    if order:
        s.last_text = order.get("text") or ""
        s.invoice = order.get("invoice") or []
        s.thread_id = order.get("thread_id") or order.get("threadId")
        s.task_status = order.get("task_status")
        s.customer_id = order.get("khach_hang_id") or order.get("khID")
        s.customer_name = order.get("kh") or order.get("customerNameOverride")
        s.kv_invoice_id = order.get("kiotvietInvoiceID") or order.get("kiotviet_invoice_id")
        s.discount = int(order.get("discount", 0))
        s.pvc = int(order.get("pvc", 0))
        s.vat = int(order.get("vat", 0))
        s.kh_debt = int(order.get("khDebt", 0))
        s.payments = order.get("payments") or []
        s.discussion_group_message_id = order.get("discussion_group_message_id")
        s.trello_card_id = order.get("trello_card_id")

    if not s.last_text:
        await bot.send_message(chat_id, f"Không tìm thấy đơn {order_id} hoặc thiếu trường 'text'.")
        store.delete(chat_id)
        return

    s.sending_initial = True
    try:
        await send_help(bot, chat_id, s)
        s.sent_initial = True
    finally:
        s.sending_initial = False
    store.reset_timer(chat_id)
