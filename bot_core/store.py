"""bot_don_hang/store.py — In-memory session state per chat."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient

from bot_core import config

_sessions: dict[int, "Session"] = {}
_bot: TelegramClient | None = None

log = logging.getLogger("bot.store")


def set_bot_client(client: TelegramClient):
    """Store bot client reference for timer callbacks."""
    global _bot
    _bot = client


@dataclass
class Session:
    chat_id: int
    order_id: str | None = None
    user_id: int | None = None
    thread_id: int | None = None
    last_text: str = ""
    invoice: list = field(default_factory=list)
    task_status: dict | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    kv_invoice_id: str | None = None
    discount: int = 0
    pvc: int = 0
    vat: int = 0
    kh_debt: int = 0
    payments: list = field(default_factory=list)
    discussion_group_message_id: int | None = None
    edit_invoice: dict | None = None          # invoice editing state
    confirm_kv: dict | None = None             # KiotViet confirm state
    confirm_payment: dict | None = None        # payment confirm state
    confirm_giao: dict | None = None           # giao hàng confirm state
    confirm_print: dict | None = None          # print confirm state
    pay_flow: dict | None = None               # nhận tiền flow state
    nop_wizard: dict | None = None             # nộp tiền wizard state
    awaiting_rename: bool = False              # rename order flow
    pending_media: dict = field(default_factory=dict)
    last_list_msg_id: int | None = None
    sent_initial: bool = False
    sending_initial: bool = False
    timer: asyncio.TimerHandle | None = None
    trello_card_id: str | None = None


def get(chat_id: int) -> Session | None:
    return _sessions.get(chat_id)


def set_(chat_id: int, session: Session):
    _sessions[chat_id] = session
    try:
        from bot_core import session_store
        session_store.save(session)
    except Exception as e:
        import logging
        logging.getLogger("bot.store").warning("persist session failed: %s", e)


def delete(chat_id: int):
    s = _sessions.get(chat_id)
    if s and s.timer:
        s.timer.cancel()
    _sessions.pop(chat_id, None)
    try:
        from bot_core import session_store
        session_store.delete(chat_id)
    except Exception as e:
        import logging
        logging.getLogger("bot.store").warning("persist delete failed: %s", e)


def reset_timer(chat_id: int):
    s = get(chat_id)
    if not s:
        return
    if s.timer:
        s.timer.cancel()
    loop = asyncio.get_running_loop()
    # Phase 1: after 30s of inactivity, remove reply keyboard (session stays alive)
    s.timer = loop.call_later(
        30,
        lambda: asyncio.ensure_future(_auto_clear_keyboard(chat_id)),
    )


async def _auto_clear_keyboard(chat_id: int):
    """Remove the reply keyboard after 30s, then schedule session clear after another 30s."""
    log.info("Auto-clear keyboard for chat %d (30s inactivity)", chat_id)
    s = get(chat_id)
    if not s:
        return
    # Remove keyboard
    if _bot is not None and s.last_list_msg_id:
        try:
            await _bot.edit_message(chat_id, s.last_list_msg_id, buttons=None)
            s.last_list_msg_id = None
        except Exception as e:
            log.warning("auto_clear_keyboard edit failed: %s", e)
    elif _bot is None:
        log.warning("auto_clear_keyboard: bot is None, cannot remove keyboard")
    # Phase 2: schedule full session clear after another 30s (60s total)
    loop = asyncio.get_running_loop()
    s.timer = loop.call_later(
        30,
        lambda: asyncio.ensure_future(_auto_clear(chat_id)),
    )


async def _auto_clear(chat_id: int):
    log.info("Auto-clear session for chat %d (60s inactivity)", chat_id)
    import bot_handlers as _handlers
    await _handlers.clear_session(chat_id, silent=False, bot=_bot)


def restore_sessions() -> None:
    """Reload in-progress sessions from SQLite on startup."""
    try:
        from bot_core import session_store
        session_store.prune_older_than(seconds=86400)  # drop > 24h old
        rows = session_store.load_all()
        for data in rows:
            chat_id = data.get("chat_id")
            if chat_id is None:
                continue
            s = Session(
                chat_id=chat_id,
                order_id=data.get("order_id"),
                user_id=data.get("user_id"),
                thread_id=data.get("thread_id"),
                last_text=data.get("last_text", ""),
                invoice=data.get("invoice", []) or [],
                task_status=data.get("task_status"),
                customer_id=data.get("customer_id"),
                customer_name=data.get("customer_name"),
                kv_invoice_id=data.get("kv_invoice_id"),
                discount=int(data.get("discount", 0) or 0),
                pvc=int(data.get("pvc", 0) or 0),
                vat=int(data.get("vat", 0) or 0),
                kh_debt=int(data.get("kh_debt", 0) or 0),
                payments=list(data.get("payments", []) or []),
                discussion_group_message_id=data.get("discussion_group_message_id"),
                trello_card_id=data.get("trello_card_id"),
            )
            _sessions[chat_id] = s
        if rows:
            log.info("Restored %d sessions from SQLite", len(rows))
    except Exception as e:
        log.warning("restore_sessions failed: %s", e)
