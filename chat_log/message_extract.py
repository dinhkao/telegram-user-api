from __future__ import annotations

from telethon.tl.types import MessageService


def sender_name(msg) -> str | None:
    sender = getattr(msg, "sender", None)
    if not sender:
        return None
    first = getattr(sender, "first_name", None)
    last = getattr(sender, "last_name", None)
    if first or last:
        return " ".join(part for part in (first, last) if part)
    return getattr(sender, "title", None) or getattr(sender, "username", None)


def media_type(msg) -> str | None:
    if isinstance(msg, MessageService):
        return "service"
    media = getattr(msg, "media", None)
    if not media:
        return None
    media_name = type(media).__name__
    if media_name.startswith("MessageMedia"):
        return media_name.removeprefix("MessageMedia").lower()
    return media_name.lower()


def message_text(msg) -> str | None:
    if isinstance(msg, MessageService):
        action = getattr(msg, "action", None)
        return type(action).__name__ if action else None
    text = (getattr(msg, "raw_text", None) or getattr(msg, "text", None) or "").strip()
    return text or None


def extract_thread_id(msg) -> int | None:
    thread_id = None
    if msg.reply_to:
        thread_id = getattr(msg.reply_to, "reply_to_top_id", None) or getattr(
            msg.reply_to, "reply_to_msg_id", None
        )
    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None) or getattr(msg, "reply_to_msg_id", None)
    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw and getattr(raw, "reply_to", None):
            reply_to = raw.reply_to
            thread_id = getattr(reply_to, "reply_to_top_id", None) or getattr(
                reply_to, "reply_to_msg_id", None
            )
    if not thread_id and isinstance(msg, MessageService):
        action_name = type(getattr(msg, "action", None)).__name__
        if "TopicCreate" in action_name:
            thread_id = getattr(msg, "id", None)
    return thread_id
