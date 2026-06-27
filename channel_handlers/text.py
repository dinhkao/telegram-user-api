from __future__ import annotations

from telethon import types


def normalize_text(text: str) -> str:
    return str(text or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")


def escape_to_backslash_n(text: str) -> str:
    return normalize_text(text).replace("\n", "\\n")


def topic_name_from_text(order_text: str) -> str:
    topic_name = order_text.replace("\\n", " ").replace("\n", " ").strip()
    return topic_name[:125] + "..." if len(topic_name) > 128 else topic_name


def should_skip_message(msg) -> bool:
    return (not msg.text) or msg.is_reply or msg.text.startswith(("!", "^", "+"))


def extract_thread_id(result):
    for update in getattr(result, "updates", []):
        if isinstance(update, types.UpdateMessageID):
            return update.id
        if hasattr(update, "message"):
            m = update.message
            if getattr(m, "reply_to", None):
                thread_id = getattr(m.reply_to, "reply_to_top_id", None) or m.reply_to.reply_to_msg_id
                if thread_id:
                    return thread_id
            if isinstance(m, types.Message):
                return m.id
    return None
