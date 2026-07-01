"""Message dispatcher — runs handlers in bot.js order; first match wins."""

from __future__ import annotations

from .context import build_context
from .handlers_lookup import handle_export, handle_start
from .handlers_sheet import handle_amount, handle_hi, handle_product, handle_quoted

# Order mirrors bot.js `bot.on('message')` branch order exactly.
_HANDLERS = [
    handle_start,
    handle_quoted,
    handle_amount,
    handle_product,
    handle_export,
    handle_hi,
]


def make_dispatcher(manager):
    async def on_message(event):
        ctx = await build_context(event, manager)
        for handler in _HANDLERS:
            if await handler(ctx):
                return

    return on_message
