"""Persists Telegram new/edited/deleted messages -> chat-log table in shared SQLite (SHARED_DB_PATH). Root shim: order_chat_logger.py."""
from .db import ORDER_GROUP_ID, SHARED_DB_PATH, init_table
from .handlers import register_chat_logger

__all__ = ["ORDER_GROUP_ID", "SHARED_DB_PATH", "init_table", "register_chat_logger"]
