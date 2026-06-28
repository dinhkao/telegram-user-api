"""bot_don_hang/flows/_helpers.py — Shared helpers for flow modules."""
import logging
import os
import sys

from bot_core import config

log = logging.getLogger("bot.flows")
ORDER_API_BASE = config.ORDER_API_BASE
USER_API_BASE = config.USER_API_BASE

# Inject telegram-user-api path so `kiotviet` can be imported (configurable).
_TGUA_PATH = os.getenv("TGUA_PATH", os.path.expanduser("~/Documents/telegram-user-api"))
if _TGUA_PATH and _TGUA_PATH not in sys.path:
    sys.path.insert(0, _TGUA_PATH)


def _nf(n) -> str:
    """Format integer with thousands separator."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)
