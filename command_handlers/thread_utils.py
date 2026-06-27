from __future__ import annotations


def extract_thread_id(msg) -> int | None:
    reply = getattr(msg, "reply_to", None)
    if reply:
        thread_id = getattr(reply, "reply_to_top_id", None) or getattr(reply, "reply_to_msg_id", None)
        if thread_id and not getattr(reply, "forum_topic", False):
            return getattr(reply, "reply_to_top_id", None)
        if thread_id:
            return thread_id
    thread_id = getattr(msg, "reply_to_top_id", None)
    if thread_id:
        return thread_id
    raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
    if raw and getattr(raw, "reply_to", None):
        return getattr(raw.reply_to, "reply_to_top_id", None)
    return None
