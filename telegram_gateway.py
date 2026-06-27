"""telegram_gateway.py - async wrapper around a Telethon client.

Provides basic global and per-chat rate limiting, edit debouncing, and
FloodWait handling so callers can use one consistent Telegram entry point.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - fallback only used when Telethon is unavailable
    from telethon.errors import FloodWaitError, MessageNotModifiedError
except Exception:  # pragma: no cover
    class FloodWaitError(Exception):
        def __init__(self, seconds: int = 0):
            super().__init__(f"Flood wait for {seconds} seconds")
            self.seconds = int(seconds)

    class MessageNotModifiedError(Exception):
        pass


log = logging.getLogger("telegram_gateway")


class TelegramRateLimited(RuntimeError):
    """Raised when Telegram asks us to sleep for too long."""

    def __init__(self, seconds: int, operation: str, max_sleep_sec: float):
        self.seconds = int(seconds)
        self.operation = operation
        self.max_sleep_sec = float(max_sleep_sec)
        super().__init__(
            f"{operation} flood wait {self.seconds}s exceeds max sleep {self.max_sleep_sec}s"
        )


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    if raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


class _TokenBucket:
    def __init__(self, rate_per_sec: float, *, capacity: float | None = None):
        self.rate_per_sec = max(0.0, float(rate_per_sec))
        if capacity is None:
            self.capacity = self.rate_per_sec if self.rate_per_sec >= 1.0 else 1.0
        else:
            self.capacity = max(0.0, float(capacity))
        self.tokens = self.capacity if self.rate_per_sec > 0 else 0.0
        self.updated_at = time.monotonic()
        self._lock: asyncio.Lock | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> None:
        if self.rate_per_sec <= 0:
            return

        async with self._ensure_lock():
            while True:
                now = time.monotonic()
                elapsed = now - self.updated_at
                if elapsed > 0:
                    self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
                    self.updated_at = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                wait_sec = (1.0 - self.tokens) / self.rate_per_sec
                await asyncio.sleep(wait_sec)


@dataclass
class _EditState:
    future: asyncio.Future | None = None
    runner: asyncio.Task | None = None
    version: int = 0
    entity: Any = None
    message_id: int = 0
    text: Any = None
    kwargs: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.kwargs is None:
            self.kwargs = {}


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
        self.global_rate_per_sec = _read_float_env("TG_RATE_GLOBAL_PER_SEC", 5.0)
        self.per_chat_rate_per_sec = _read_float_env("TG_RATE_PER_CHAT_PER_SEC", 1.0)
        self.edit_debounce_sec = max(0.0, _read_float_env("TG_RATE_EDIT_DEBOUNCE_SEC", 0.25))
        self.flood_max_sleep_sec = max(0.0, _read_float_env("TG_FLOOD_MAX_SLEEP_SEC", 60.0))

        if global_rate_per_sec is not None:
            self.global_rate_per_sec = float(global_rate_per_sec)
        if per_chat_rate_per_sec is not None:
            self.per_chat_rate_per_sec = float(per_chat_rate_per_sec)
        if edit_debounce_sec is not None:
            self.edit_debounce_sec = max(0.0, float(edit_debounce_sec))
        if flood_max_sleep_sec is not None:
            self.flood_max_sleep_sec = max(0.0, float(flood_max_sleep_sec))

        self._global_bucket = _TokenBucket(self.global_rate_per_sec)
        self._chat_buckets: dict[Any, _TokenBucket] = {}
        self._edit_states: dict[tuple[Any, int], _EditState] = {}
        self._edit_states_lock: asyncio.Lock | None = None

    def install(self) -> None:
        """Route common client calls through this gateway instance."""
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

    def _chat_bucket_for(self, entity: Any) -> _TokenBucket:
        key = self._entity_key(entity)
        bucket = self._chat_buckets.get(key)
        if bucket is None:
            bucket = _TokenBucket(self.per_chat_rate_per_sec, capacity=1.0)
            self._chat_buckets[key] = bucket
        return bucket

    async def _acquire_rate_limit(self, entity: Any) -> None:
        await self._global_bucket.acquire()
        await self._chat_bucket_for(entity).acquire()

    async def _call_with_retry(self, operation: str, call) -> Any:
        while True:
            try:
                return await call()
            except FloodWaitError as exc:
                seconds = max(0, int(getattr(exc, "seconds", 0) or 0))
                if seconds > self.flood_max_sleep_sec:
                    raise TelegramRateLimited(seconds, operation, self.flood_max_sleep_sec) from exc
                log.warning(
                    "%s flood_wait seconds=%s max_sleep=%s; sleeping",
                    operation,
                    seconds,
                    self.flood_max_sleep_sec,
                )
                await asyncio.sleep(seconds)

    async def _run_operation(self, operation: str, entity: Any, call) -> Any:
        start = time.perf_counter()
        log.info("%s start entity=%r", operation, entity)
        try:
            await self._acquire_rate_limit(entity)
            result = await self._call_with_retry(operation, call)
            log.info(
                "%s ok entity=%r duration=%.3fs",
                operation,
                entity,
                time.perf_counter() - start,
            )
            return result
        except MessageNotModifiedError:
            raise
        except TelegramRateLimited:
            log.warning(
                "%s rate_limited entity=%r duration=%.3fs",
                operation,
                entity,
                time.perf_counter() - start,
            )
            raise
        except Exception:
            log.exception(
                "%s error entity=%r duration=%.3fs",
                operation,
                entity,
                time.perf_counter() - start,
            )
            raise

    async def send_message(self, entity: Any, message: Any, **kwargs: Any) -> Any:
        return await self._run_operation(
            "send_message",
            entity,
            lambda: self._orig_send_message(entity=entity, message=message, **kwargs),
        )

    async def send_file(self, entity: Any, file: Any, **kwargs: Any) -> Any:
        return await self._run_operation(
            "send_file",
            entity,
            lambda: self._orig_send_file(entity=entity, file=file, **kwargs),
        )

    async def delete_messages(self, entity: Any, message_ids: Any, **kwargs: Any) -> Any:
        return await self._run_operation(
            "delete_messages",
            entity,
            lambda: self._orig_delete_messages(entity, message_ids, **kwargs),
        )

    async def get_messages(self, entity: Any, **kwargs: Any) -> Any:
        return await self._run_operation(
            "get_messages",
            entity,
            lambda: self._orig_get_messages(entity, **kwargs),
        )

    async def edit_message(
        self,
        entity: Any,
        message_id: int | None = None,
        text: Any = None,
        **kwargs: Any,
    ) -> Any:
        if message_id is None:
            message_id = kwargs.pop("message")
        else:
            kwargs.pop("message", None)
        if text is None and "text" in kwargs:
            text = kwargs.pop("text")
        key = self._edit_key(entity, message_id)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any]

        async with self._ensure_edit_states_lock():
            state = self._edit_states.get(key)
            if state is None:
                state = _EditState()
                self._edit_states[key] = state

            state.version += 1
            state.entity = entity
            state.message_id = int(message_id)
            state.text = text
            state.kwargs = dict(kwargs)

            if state.future is None or state.future.done():
                state.future = loop.create_future()

            if state.runner is None or state.runner.done():
                state.runner = loop.create_task(self._run_edit_task(key))

            future = state.future

        return await future

    async def _run_edit_task(self, key: tuple[Any, int]) -> None:
        while True:
            await asyncio.sleep(self.edit_debounce_sec)

            async with self._ensure_edit_states_lock():
                state = self._edit_states.get(key)
                if state is None:
                    return
                version = state.version
                entity = state.entity
                message_id = state.message_id
                text = state.text
                kwargs = dict(state.kwargs)
                future = state.future

            operation = f"edit_message[{message_id}]"
            error: Exception | None = None
            result: Any = None
            try:
                result = await self._run_operation(
                    operation,
                    entity,
                    lambda: self._orig_edit_message(
                        entity=entity,
                        message=message_id,
                        text=text,
                        **kwargs,
                    ),
                )
            except MessageNotModifiedError:
                result = None
            except Exception as exc:
                error = exc

            async with self._ensure_edit_states_lock():
                state = self._edit_states.get(key)
                if state is None:
                    return

                if state.version != version:
                    continue

                self._edit_states.pop(key, None)

                if future is not None and not future.done():
                    if error is None:
                        future.set_result(result)
                    else:
                        future.set_exception(error)
                return
