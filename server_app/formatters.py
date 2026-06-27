from __future__ import annotations


def sender_info(sender) -> dict:
    if not sender:
        return {"name": "Unknown", "id": 0}
    if hasattr(sender, "title"):
        name = sender.title + (f" (@{sender.username})" if getattr(sender, "username", None) else "")
        return {"name": name, "id": sender.id, "is_channel": True}
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    if getattr(sender, "username", None):
        name += f" (@{sender.username})"
    return {"name": name, "id": sender.id, "is_channel": False}
