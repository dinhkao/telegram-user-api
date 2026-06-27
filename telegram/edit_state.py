from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EditState:
    future: asyncio.Future | None = None
    runner: asyncio.Task | None = None
    version: int = 0
    entity: Any = None
    message_id: int = 0
    text: Any = None
    kwargs: dict[str, Any] = field(default_factory=dict)


__all__ = ["EditState"]
