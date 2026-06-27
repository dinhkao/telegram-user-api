from __future__ import annotations

from typing import Any

try:  # pragma: no cover - prefer Telethon when available
    from telethon.errors import FloodWaitError, MessageNotModifiedError
except Exception:  # pragma: no cover
    class FloodWaitError(Exception):
        def __init__(
            self,
            *args: Any,
            request: Any = None,
            capture: int | None = None,
            seconds: int | None = None,
            **kwargs: Any,
        ) -> None:
            value = seconds if seconds is not None else capture
            if value is None and args:
                value = args[0]
            self.request = request
            self.seconds = int(value or 0)
            super().__init__(f"Flood wait for {self.seconds} seconds")

    class MessageNotModifiedError(Exception):
        pass


class TelegramRateLimited(RuntimeError):
    def __init__(self, seconds: int, operation: str, max_sleep_sec: float):
        self.seconds = int(seconds)
        self.operation = operation
        self.max_sleep_sec = float(max_sleep_sec)
        super().__init__(
            f"{operation} flood wait {self.seconds}s exceeds max sleep {self.max_sleep_sec}s"
        )


__all__ = ["FloodWaitError", "MessageNotModifiedError", "TelegramRateLimited"]
