"""bot_core/store.py — In-memory session state per chat."""
import asyncio, logging
from dataclasses import dataclass, field
from typing import Any
from telethon import TelegramClient
from bot_core import config

_sessions: dict[int, "Session"] = {}
log = logging.getLogger("bot.store")

def set_bot_client(client: TelegramClient):
    from bot_core.store_timer import set_bot_client as _set
    _set(client)

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
    edit_invoice: dict | None = None
    confirm_kv: dict | None = None
    confirm_payment: dict | None = None
    confirm_giao: dict | None = None
    confirm_print: dict | None = None
    pay_flow: dict | None = None
    nop_wizard: dict | None = None
    awaiting_rename: bool = False
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
        log.warning("persist session failed: %s", e)

def delete(chat_id: int):
    s = _sessions.get(chat_id)
    if s and s.timer:
        s.timer.cancel()
    _sessions.pop(chat_id, None)
    try:
        from bot_core import session_store
        session_store.delete(chat_id)
    except Exception as e:
        log.warning("persist delete failed: %s", e)

def reset_timer(chat_id: int):
    from bot_core.store_timer import reset_timer as _rt
    _rt(chat_id)

def restore_sessions() -> None:
    try:
        from bot_core import session_store
        session_store.prune_older_than(seconds=86400)
        rows = session_store.load_all()
        for data in rows:
            chat_id = data.get("chat_id")
            if chat_id is None:
                continue
            s = Session(
                chat_id=chat_id, order_id=data.get("order_id"),
                user_id=data.get("user_id"), thread_id=data.get("thread_id"),
                last_text=data.get("last_text", ""), invoice=data.get("invoice", []) or [],
                task_status=data.get("task_status"), customer_id=data.get("customer_id"),
                customer_name=data.get("customer_name"), kv_invoice_id=data.get("kv_invoice_id"),
                discount=int(data.get("discount", 0) or 0), pvc=int(data.get("pvc", 0) or 0),
                vat=int(data.get("vat", 0) or 0), kh_debt=int(data.get("kh_debt", 0) or 0),
                payments=list(data.get("payments", []) or []),
                discussion_group_message_id=data.get("discussion_group_message_id"),
                trello_card_id=data.get("trello_card_id"),
            )
            _sessions[chat_id] = s
        if rows:
            log.info("Restored %d sessions from SQLite", len(rows))
    except Exception as e:
        log.warning("restore_sessions failed: %s", e)
