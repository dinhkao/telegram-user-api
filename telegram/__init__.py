"""Telegram gateway: rate-limit bucket, edit-state, flood-wait errors, safe send/edit ops over Telethon. Root shim: telegram_gateway.py."""
from __future__ import annotations

from .errors import FloodWaitError, MessageNotModifiedError, TelegramRateLimited
from .gateway import TelegramGateway

__all__ = [
    "TelegramGateway",
    "TelegramRateLimited",
    "FloodWaitError",
    "MessageNotModifiedError",
]
