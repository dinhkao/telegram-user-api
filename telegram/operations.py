from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .errors import FloodWaitError, MessageNotModifiedError, TelegramRateLimited


log = logging.getLogger("telegram_gateway")


async def call_with_retry(
    operation: str, call: Callable[[], Awaitable[Any]], max_sleep_sec: float
) -> Any:
    while True:
        try:
            return await call()
        except FloodWaitError as exc:
            seconds = max(0, int(getattr(exc, "seconds", 0) or 0))
            if seconds > max_sleep_sec:
                raise TelegramRateLimited(seconds, operation, max_sleep_sec) from exc
            log.warning("%s flood_wait seconds=%s max_sleep=%s; sleeping", operation, seconds, max_sleep_sec)
            await asyncio.sleep(seconds)


async def run_operation(
    operation: str,
    entity: Any,
    acquire_rate_limit: Callable[[Any], Awaitable[None]],
    call: Callable[[], Awaitable[Any]],
    max_sleep_sec: float,
) -> Any:
    start = time.perf_counter()
    log.info("%s start entity=%r", operation, entity)
    try:
        await acquire_rate_limit(entity)
        result = await call_with_retry(operation, call, max_sleep_sec)
        log.info("%s ok entity=%r duration=%.3fs", operation, entity, time.perf_counter() - start)
        return result
    except MessageNotModifiedError:
        raise
    except TelegramRateLimited:
        log.warning("%s rate_limited entity=%r duration=%.3fs", operation, entity, time.perf_counter() - start)
        raise
    except Exception:
        log.exception("%s error entity=%r duration=%.3fs", operation, entity, time.perf_counter() - start)
        raise


__all__ = ["call_with_retry", "run_operation"]
