"""MsgCtx — normalized per-message context passed to handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..parse import normalize_product_code
from .telegram_ctx import (
    build_message_deep_link,
    build_thread_url,
    format_sender_name,
    thread_id_of,
)


@dataclass
class MsgCtx:
    client: Any
    event: Any
    message: Any
    manager: Any
    chat: Any
    chat_id: int
    raw_text: str
    text: str
    product_code: str
    is_private: bool
    is_group: bool
    thread_id: Any
    message_id: Any
    thread_url: str
    reply_thread: Any
    is_quoted: bool
    _sender_name: Any = None

    async def sender_name(self) -> str:
        if self._sender_name is None:
            self._sender_name = format_sender_name(await self.event.get_sender())
        return self._sender_name

    def deep_link(self) -> str:
        return build_message_deep_link(self.chat, self.chat_id, self.message_id)


async def build_context(event, manager) -> MsgCtx:
    message = event.message
    raw_text = (message.text or "").strip()
    chat = await event.get_chat()
    tid = thread_id_of(message)
    return MsgCtx(
        client=event.client,
        event=event,
        message=message,
        manager=manager,
        chat=chat,
        chat_id=event.chat_id,
        raw_text=raw_text,
        text=raw_text.lower(),
        product_code=normalize_product_code(raw_text),
        is_private=bool(event.is_private),
        is_group=bool(event.is_group),
        thread_id=tid,
        message_id=message.id,
        thread_url=build_thread_url(chat, event.chat_id, tid),
        reply_thread=tid if tid else None,
        is_quoted=raw_text.startswith('"') and raw_text.endswith('"') and len(raw_text) >= 2,
    )
