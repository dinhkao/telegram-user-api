from __future__ import annotations

import json


def safe_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def build_raw_json(msg, *, event_type: str, thread_id: int | None, extra: dict | None = None) -> str:
    payload = msg.to_dict() if hasattr(msg, "to_dict") else {"message_id": getattr(msg, "id", None)}
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    payload.update({"logger_event_type": event_type, "logger_thread_id": thread_id})
    if extra:
        payload.update(extra)
    return safe_json(payload)


def build_delete_raw_json(*, message_id: int, deleted_ids: list[int], chat_id: int | None) -> str:
    return safe_json(
        {
            "logger_event_type": "delete",
            "message_id": message_id,
            "deleted_ids": deleted_ids,
            "chat_id": chat_id,
        }
    )
