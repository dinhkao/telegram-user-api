from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import web
    from donhang_db import DonHangDB
    from telegram_gateway import TelegramGateway
    from telethon import TelegramClient

ws_clients: set["web.WebSocketResponse"] = set()
_client: "TelegramClient | None" = None
_tg_gateway: "TelegramGateway | None" = None
_donhang_db: "DonHangDB | None" = None
duy_user_id: int | None = None


def set_client(client):
    global _client
    _client = client


def set_gateway(gateway):
    global _tg_gateway
    _tg_gateway = gateway


def set_donhang_db(db):
    global _donhang_db
    _donhang_db = db


def set_duy_user_id(user_id: int):
    global duy_user_id
    duy_user_id = user_id

