"""sheets_bot.bot — Telethon bot entrypoint (split by concern)."""

from .entry import get_client, get_manager, start_sheets_bot

__all__ = ["start_sheets_bot", "get_manager", "get_client"]
