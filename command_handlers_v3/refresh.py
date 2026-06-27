"""Compatibility exports for refresh helpers."""
from __future__ import annotations

from order_commands_v3 import (
    _EditBatcher,
    _firebase_and_refresh,
    _firebase_refresh_async,
    _refresh_order_if_possible,
    _refresh_order_message,
)


def get_edit_batcher():
    import order_commands_v3

    return getattr(order_commands_v3, "_edit_batcher", None)


def set_edit_batcher(edit_batcher):
    import order_commands_v3

    order_commands_v3._edit_batcher = edit_batcher


__all__ = [
    "_EditBatcher",
    "_firebase_and_refresh",
    "_firebase_refresh_async",
    "_refresh_order_if_possible",
    "_refresh_order_message",
    "get_edit_batcher",
    "set_edit_batcher",
]

