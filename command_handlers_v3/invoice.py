"""Compatibility access to legacy invoice handlers."""
from __future__ import annotations


def __getattr__(name):
    import order_commands_v3

    return getattr(order_commands_v3, name)

