"""start_sheets_bot — construct the client, wire dispatch, run startup migration."""

from __future__ import annotations

import logging

from telethon import TelegramClient, events

from .. import config
from .dispatch import make_dispatcher

log = logging.getLogger("sheets_bot.bot")

_client: TelegramClient | None = None
_manager = None


async def start_sheets_bot(api_id, api_hash):
    """Start the sheets bot. Returns the TelegramClient, or None if unconfigured."""
    global _client, _manager

    token = config.bot_token()
    if not token or config.is_placeholder(token):
        log.warning("SHEETS_BOT_TOKEN/TELEGRAM_BOT_TOKEN not set — sheets bot skipped")
        return None
    if not config.has_credentials():
        log.warning(
            "Google credentials not configured "
            "(GOOGLE_APPLICATION_CREDENTIALS[_JSON|_B64]) — sheets bot skipped"
        )
        return None

    from ..sheets import SheetsManager

    _manager = SheetsManager()

    _client = TelegramClient("sheets_bot_session", api_id, api_hash)
    await _client.start(bot_token=token)
    me = await _client.get_me()
    log.info("Sheets bot started as @%s (id=%s)", getattr(me, "username", None), me.id)

    _client.add_event_handler(make_dispatcher(_manager), events.NewMessage(incoming=True))

    try:
        await _manager.migrate_existing_managed_sheets()
        log.info("Managed sheet header migration completed.")
    except Exception as err:  # noqa: BLE001
        log.error("Failed to migrate existing managed sheets: %s", err)

    return _client


def get_manager():
    return _manager


def get_client():
    return _client
