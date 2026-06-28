"""bot_core/store_timer.py — Session timer: auto-clear keyboard & session."""
import asyncio
import logging

from telethon import TelegramClient

log = logging.getLogger("bot.store")

# Will be set by store.py or bot_bootstrap
_bot: "TelegramClient | None" = None


def set_bot_client(client: "TelegramClient"):
    global _bot
    _bot = client


def get_bot_client():
    return _bot


def reset_timer(chat_id: int):
    from bot_core.store import get
    s = get(chat_id)
    if not s:
        return
    if s.timer:
        s.timer.cancel()
    loop = asyncio.get_running_loop()
    s.timer = loop.call_later(
        30,
        lambda: asyncio.ensure_future(_auto_clear_keyboard(chat_id)),
    )


async def _auto_clear_keyboard(chat_id: int):
    """Remove reply keyboard after 30s, then schedule session clear."""
    log.info("Auto-clear keyboard for chat %d (30s inactivity)", chat_id)
    from bot_core.store import get
    s = get(chat_id)
    if not s:
        return
    if _bot is not None and s.last_list_msg_id:
        try:
            await _bot.edit_message(chat_id, s.last_list_msg_id, buttons=None)
            s.last_list_msg_id = None
        except Exception as e:
            log.warning("auto_clear_keyboard edit failed: %s", e)
    elif _bot is None:
        log.warning("auto_clear_keyboard: bot is None")
    loop = asyncio.get_running_loop()
    s.timer = loop.call_later(
        30,
        lambda: asyncio.ensure_future(_auto_clear(chat_id)),
    )


async def _auto_clear(chat_id: int):
    log.info("Auto-clear session for chat %d (60s inactivity)", chat_id)
    import bot_handlers as _handlers
    from bot_core.store import get
    await _handlers.clear_session(chat_id, silent=False, bot=_bot)
