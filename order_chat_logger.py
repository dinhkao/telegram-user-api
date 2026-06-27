"""order_chat_logger.py - wrapper cho chat_log.

Giữ nguyên API công khai để import cũ vẫn chạy.
"""

from chat_log import init_table, register_chat_logger

__all__ = ["init_table", "register_chat_logger"]
