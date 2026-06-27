"""Compatibility wrapper for the Telegram gateway."""

from __future__ import annotations

import asyncio  # kept for tests that patch telegram_gateway.asyncio.sleep

from telegram import FloodWaitError, MessageNotModifiedError, TelegramGateway, TelegramRateLimited

__all__ = [
    "TelegramGateway",
    "TelegramRateLimited",
    "FloodWaitError",
    "MessageNotModifiedError",
]
