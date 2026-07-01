"""Handles new #don_hang channel posts: parse/render/notify/register -> order_store, Firebase, KiotViet. Root shim: channel_handler.py."""
from .register import register

__all__ = ["register"]
