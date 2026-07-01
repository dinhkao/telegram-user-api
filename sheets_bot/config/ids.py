"""Env-derived spreadsheet ids / gids and bot token (same defaults as bot.js).

These are document ids, not secrets; tokens/credentials are never hardcoded.
"""

from __future__ import annotations

import os


def spreadsheet_id() -> str:
    return os.getenv("SPREADSHEET_ID") or "18n-W71c81rYHfFR1eq6rp-YLml8301UW4XhmJtcYvqo"


def topic_spreadsheet_id() -> str:
    return os.getenv("TOPIC_SPREADSHEET_ID") or "1zSCustpTviHF4-bb8BrFft_K8wdZ9pYUFbsh2eoqyVk"


def topic_sheet_gid() -> int:
    return int(os.getenv("TOPIC_SHEET_GID") or "1962815338")


def allowed_products_gid() -> int:
    return int(os.getenv("ALLOWED_PRODUCTS_GID") or "811594671")


def allowed_products_cache_ms() -> int:
    return int(os.getenv("ALLOWED_PRODUCTS_CACHE_MS") or "300000")


def import_sheet_gid() -> int:
    return int(os.getenv("IMPORT_SHEET_GID") or "2031606130")


def bot_token() -> str | None:
    return os.getenv("SHEETS_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")


def is_placeholder(val: str | None) -> bool:
    if not val:
        return True
    v = val.lower()
    return (
        "your_telegram_bot_token" in v
        or "your_sheet_id" in v
        or "path/to/credentials.json" in v
    )
