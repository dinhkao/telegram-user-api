from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rate_per_sec: float, *, capacity: float | None = None):
        self.rate_per_sec = max(0.0, float(rate_per_sec))
        self.capacity = (
            self.rate_per_sec if capacity is None and self.rate_per_sec >= 1.0 else 1.0
        )
        if capacity is not None:
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
                await asyncio.sleep((1.0 - self.tokens) / self.rate_per_sec)


__all__ = ["TokenBucket"]
