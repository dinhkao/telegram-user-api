from __future__ import annotations

import logging

from telethon import events

from .config import CHANNEL_DON_HANG_MOI
from .create import process_new_order

log = logging.getLogger("channel_handler")


def register(client):
    @client.on(events.NewMessage(chats=CHANNEL_DON_HANG_MOI))
    async def on_channel_post(event):
        # Tin gõ tay trên Telegram (incoming) → tạo topic + đơn. Tin do CHÍNH client
        # gửi (đơn từ web) KHÔNG kích hoạt event này — web gọi thẳng process_new_order.
        await process_new_order(client, event.message)
