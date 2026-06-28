"""server_app/bot_bootstrap.py — Start bot Telethon client (merged from bot-don-hang).

Runs alongside the user client in the same process.
"""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient

from bot_core import config, store
from bot_core.session_store import SESSION_DB

log = logging.getLogger("bot_bootstrap")

_bot_client: TelegramClient | None = None


def get_bot_client() -> TelegramClient | None:
    return _bot_client


async def start_bot(api_id: int, api_hash: str):
    """Initialize and start the bot client. Call from bootstrap.main()."""
    global _bot_client

    token = config.BOT_TOKEN
    if not token:
        log.warning("BOT_TOKEN not set — bot client skipped")
        return

    _bot_client = TelegramClient("bot_session", api_id, api_hash)
    await _bot_client.start(bot_token=token)
    me = await _bot_client.get_me()
    log.info("Bot started as @%s (id=%d)", me.username, me.id)

    store.set_bot_client(_bot_client)

    # Register all handlers
    from bot_handlers import register_all
    register_all(_bot_client)

    # Restore sessions from SQLite
    store.restore_sessions()

    # Pre-warm Playwright Chromium for invoice HTML→PNG
    try:
        from bot_core import html_to_png
        html_to_png.prewarm()
    except Exception as e:
        log.warning("Playwright prewarm failed: %s", e)

    # Background periodic persistence
    asyncio.create_task(_persist_loop(), name="bot_session_persist")

    log.info("Bot client ready. Session DB: %s", SESSION_DB)


async def _persist_loop():
    """Persist all active sessions every 60s."""
    from bot_core import store as _store, session_store
    while True:
        try:
            await asyncio.sleep(60)
            for s in _store._sessions.values():
                session_store.save(s)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("bot persist loop error: %s", e)
