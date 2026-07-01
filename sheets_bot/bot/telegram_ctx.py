"""Telethon-event -> Bot-API-style field extraction (urls, thread id, names)."""

from __future__ import annotations

from urllib.parse import quote


def thread_id_of(message):
    r = getattr(message, "reply_to", None)
    if r is not None and getattr(r, "forum_topic", False):
        return getattr(r, "reply_to_top_id", None) or getattr(r, "reply_to_msg_id", None)
    return None


def format_sender_name(sender) -> str:
    if not sender:
        return ""
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    full = " ".join(
        p for p in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if p
    )
    return full or str(getattr(sender, "id", "") or "")


def _internal_id(chat_id) -> str:
    internal = str(abs(int(chat_id)))
    if internal.startswith("100"):
        internal = internal[3:]
    return internal


def build_thread_url(chat, chat_id, thread_id) -> str:
    if not thread_id or chat is None:
        return ""
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{thread_id}"
    if chat_id:
        return f"https://t.me/c/{_internal_id(chat_id)}/{thread_id}"
    return ""


def build_message_deep_link(chat, chat_id, message_id) -> str:
    if not message_id or chat is None:
        return ""
    username = getattr(chat, "username", None)
    if username:
        return f"tg://resolve?domain={quote(str(username))}&post={quote(str(message_id))}"
    if chat_id:
        return f"tg://privatepost?channel={quote(_internal_id(chat_id))}&post={quote(str(message_id))}"
    return ""
