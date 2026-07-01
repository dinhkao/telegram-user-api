"""start_sheets_bot — attach sheet handlers to the user-account client.

Runs on the existing Telethon *user* session (no dedicated bot token), so it
replies as the user account and never conflicts with the railway bot's poller.
"""

from __future__ import annotations

import logging
import os

from telethon import TelegramClient, events

from .. import config
from .dispatch import make_dispatcher

log = logging.getLogger("sheets_bot.bot")

_client: TelegramClient | None = None
_manager = None


async def start_sheets_bot(client):
    """Attach sheet handlers to the given (user-account) client.

    Returns the client, or None if Google credentials are unconfigured.
    """
    global _client, _manager

    if not config.has_credentials():
        log.warning(
            "Google credentials not configured "
            "(GOOGLE_APPLICATION_CREDENTIALS[_JSON|_B64]) — sheets bot skipped"
        )
        return None

    from ..sheets import SheetsManager

    _manager = SheetsManager()
    _client = client

    # Listen to BOTH incoming and outgoing: on a user account the owner (Duy)
    # often types the rows himself, which are *outgoing* — incoming=True would
    # miss them. Handlers self-gate (group + amount + managed-thread), and the
    # bot's own "Đã thêm…" reply matches no handler, so there is no self-loop.
    client.add_event_handler(make_dispatcher(_manager), events.NewMessage())
    me = await client.get_me()
    log.info(
        "Sheets handlers attached to user account @%s (id=%s)",
        getattr(me, "username", None),
        me.id,
    )

    # Bulk header backfill over ALL existing sheets is opt-in: it does 2-3 writes
    # per sheet and blows the 60-writes/min Sheets quota, which would 429 a live
    # paste. New writes ensure their own headers on demand, so this is optional.
    if os.getenv("SHEETS_MIGRATE_ON_START", "").lower() in ("1", "true", "yes"):
        try:
            await _manager.migrate_existing_managed_sheets()
            log.info("Managed sheet header migration completed.")
        except Exception as err:  # noqa: BLE001
            log.error("Failed to migrate existing managed sheets: %s", err)

    return client


def get_manager():
    return _manager


def get_client():
    return _client
