from __future__ import annotations

import asyncio
from typing import Any

from .bucket import TokenBucket
from .editing import edit_message as _edit_message
from .env import read_float_env
from .operations import run_operation


class TelegramGateway:
    def __init__(
        self,
        client: Any,
        *,
        global_rate_per_sec: float | None = None,
        per_chat_rate_per_sec: float | None = None,
        edit_debounce_sec: float | None = None,
        flood_max_sleep_sec: float | None = None,
    ) -> None:
        self.client = client
        self._orig_send_message = client.send_message
        self._orig_edit_message = client.edit_message
        self._orig_send_file = client.send_file
        self._orig_delete_messages = client.delete_messages
        self._orig_get_messages = client.get_messages
        self.global_rate_per_sec = read_float_env("TG_RATE_GLOBAL_PER_SEC", 5.0)
        self.per_chat_rate_per_sec = read_float_env("TG_RATE_PER_CHAT_PER_SEC", 1.0)
        self.edit_debounce_sec = max(0.0, read_float_env("TG_RATE_EDIT_DEBOUNCE_SEC", 0.25))
        self.flood_max_sleep_sec = max(0.0, read_float_env("TG_FLOOD_MAX_SLEEP_SEC", 60.0))
        if global_rate_per_sec is not None:
            self.global_rate_per_sec = float(global_rate_per_sec)
        if per_chat_rate_per_sec is not None:
            self.per_chat_rate_per_sec = float(per_chat_rate_per_sec)
        if edit_debounce_sec is not None:
            self.edit_debounce_sec = max(0.0, float(edit_debounce_sec))
        if flood_max_sleep_sec is not None:
            self.flood_max_sleep_sec = max(0.0, float(flood_max_sleep_sec))
        self._global_bucket = TokenBucket(self.global_rate_per_sec)
        self._chat_buckets: dict[Any, TokenBucket] = {}
        self._edit_states: dict[tuple[Any, int], Any] = {}
        self._edit_states_lock: asyncio.Lock | None = None

    def install(self) -> None:
        self.client.send_message = self.send_message
        self.client.edit_message = self.edit_message
        self.client.send_file = self.send_file
        self.client.delete_messages = self.delete_messages
        self.client.get_messages = self.get_messages

    def _ensure_edit_states_lock(self) -> asyncio.Lock:
        if self._edit_states_lock is None:
            self._edit_states_lock = asyncio.Lock()
        return self._edit_states_lock

    def _entity_key(self, entity: Any) -> Any:
        try:
            hash(entity)
        except TypeError:
            return repr(entity)
        return entity

    def _edit_key(self, entity: Any, message_id: int) -> tuple[Any, int]:
        return self._entity_key(entity), int(message_id)

    def _chat_bucket_for(self, entity: Any) -> TokenBucket:
        key = self._entity_key(entity)
        bucket = self._chat_buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.per_chat_rate_per_sec, capacity=1.0)
            self._chat_buckets[key] = bucket
        return bucket

    async def _acquire_rate_limit(self, entity: Any) -> None:
        await self._global_bucket.acquire()
        await self._chat_bucket_for(entity).acquire()

    async def send_message(self, entity: Any, message: Any, **kwargs: Any) -> Any:
        return await run_operation("send_message", entity, self._acquire_rate_limit, lambda: self._orig_send_message(entity=entity, message=message, **kwargs), self.flood_max_sleep_sec)

    async def send_file(self, entity: Any, file: Any, **kwargs: Any) -> Any:
        return await run_operation("send_file", entity, self._acquire_rate_limit, lambda: self._orig_send_file(entity=entity, file=file, **kwargs), self.flood_max_sleep_sec)

    async def delete_messages(self, entity: Any, message_ids: Any, **kwargs: Any) -> Any:
        return await run_operation("delete_messages", entity, self._acquire_rate_limit, lambda: self._orig_delete_messages(entity, message_ids, **kwargs), self.flood_max_sleep_sec)

    async def get_messages(self, entity: Any, **kwargs: Any) -> Any:
        return await run_operation("get_messages", entity, self._acquire_rate_limit, lambda: self._orig_get_messages(entity, **kwargs), self.flood_max_sleep_sec)

    async def edit_message(self, entity: Any, message_id: int | None = None, text: Any = None, **kwargs: Any) -> Any:
        return await _edit_message(self, entity, message_id=message_id, text=text, **kwargs)


__all__ = ["TelegramGateway"]
