from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import max_field_chars, log, shared_db_path
from .db import _coerce_int, _coerce_text, _connect, _json_text, init_audit_db


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_request_id() -> str:
    return uuid.uuid4().hex


def log_event(
    action: str,
    *,
    request_id: str | None = None,
    actor_type: str | None = None,
    actor_id: str | int | None = None,
    direction: str | None = None,
    source: str | None = None,
    chat_id: int | str | None = None,
    thread_id: int | str | None = None,
    message_id: int | str | None = None,
    payload: Any = None,
    result: Any = None,
    error: Any = None,
    duration_ms: int | float | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> int | None:
    path = shared_db_path(db_path)
    limit = max_field_chars()
    try:
        init_audit_db(path)
        conn = _connect(path)
        try:
            payload_json = _json_text(payload, max_field_chars=limit)
            result_json = _json_text(result, max_field_chars=limit)
            error_text = _coerce_text(error, max_field_chars=limit)
            if duration_ms is None:
                duration_value = None
            else:
                try:
                    duration_value = int(round(float(duration_ms)))
                except (TypeError, ValueError):
                    log.warning("audit field duration_ms is not numeric: %r", duration_ms)
                    duration_value = None
            cursor = conn.execute(
                """
                INSERT INTO audit_events (
                    ts, request_id, actor_type, actor_id, action, direction, source,
                    chat_id, thread_id, message_id, payload_json, result_json, error, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    request_id or new_request_id(),
                    _coerce_text(actor_type, max_field_chars=limit),
                    _coerce_text(actor_id, max_field_chars=limit),
                    _coerce_text(action, max_field_chars=limit) or "",
                    _coerce_text(direction, max_field_chars=limit),
                    _coerce_text(source, max_field_chars=limit),
                    _coerce_int(chat_id, "chat_id"),
                    _coerce_int(thread_id, "thread_id"),
                    _coerce_int(message_id, "message_id"),
                    payload_json,
                    result_json,
                    error_text,
                    duration_value,
                ),
            )
            return cursor.lastrowid
        finally:
            conn.close()
    except Exception as exc:
        log.warning("Failed to log audit event action=%r at %s: %s", action, path, exc, exc_info=True)
        return None


async def async_log_event(*args: Any, **kwargs: Any) -> int | None:
    return await asyncio.to_thread(log_event, *args, **kwargs)

