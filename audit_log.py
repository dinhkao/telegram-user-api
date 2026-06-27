"""audit_log.py - SQLite audit trail for precise action tracking.

Best-effort helpers for recording user/server actions into shared SQLite.
Errors are logged as warnings and never raised to callers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("audit_log")

DEFAULT_SHARED_DB_PATH = "~/letrang-db/app.db"
DEFAULT_MAX_FIELD_CHARS = 4096
REDACTED_TEXT = "[REDACTED]"
TRUNCATED_SUFFIX = "...<truncated>"
SENSITIVE_KEY_HINTS = (
    "api_key",
    "api hash",
    "api_hash",
    "authorization",
    "private_key",
    "phone",
    "password",
    "session",
    "token",
)
COMPACT_SENSITIVE_KEY_HINTS = tuple(
    "".join(ch.lower() for ch in hint if ch.isalnum()) for hint in SENSITIVE_KEY_HINTS
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    request_id   TEXT,
    actor_type   TEXT,
    actor_id     TEXT,
    action       TEXT NOT NULL,
    direction    TEXT,
    source       TEXT,
    chat_id      INTEGER,
    thread_id    INTEGER,
    message_id   INTEGER,
    payload_json TEXT,
    result_json  TEXT,
    error        TEXT,
    duration_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts);
CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_thread_id ON audit_events(thread_id);
"""

__all__ = [
    "DEFAULT_SHARED_DB_PATH",
    "DEFAULT_MAX_FIELD_CHARS",
    "init_audit_db",
    "log_event",
    "async_log_event",
    "new_request_id",
    "redact_payload",
]


def _shared_db_path(db_path: str | os.PathLike[str] | None = None) -> str:
    path = os.fspath(db_path) if db_path is not None else os.getenv("SHARED_DB_PATH", DEFAULT_SHARED_DB_PATH)
    return os.path.expanduser(path)


def _max_field_chars() -> int:
    raw = os.getenv("AUDIT_MAX_FIELD_CHARS")
    if not raw:
        return DEFAULT_MAX_FIELD_CHARS
    try:
        value = int(raw)
        return value if value > 0 else DEFAULT_MAX_FIELD_CHARS
    except (TypeError, ValueError):
        log.warning("AUDIT_MAX_FIELD_CHARS invalid=%r; using default %d", raw, DEFAULT_MAX_FIELD_CHARS)
        return DEFAULT_MAX_FIELD_CHARS


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_request_id() -> str:
    """Create a stable request ID for correlating audit rows."""
    return uuid.uuid4().hex


def _normalize_key(key: Any) -> str:
    if not isinstance(key, str):
        key = str(key)
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in key)


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    compact = "".join(ch for ch in normalized if ch.isalnum())
    return any(hint in normalized for hint in (hint.replace(" ", "_") for hint in SENSITIVE_KEY_HINTS)) or any(
        hint in compact for hint in COMPACT_SENSITIVE_KEY_HINTS
    )


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + TRUNCATED_SUFFIX


def _normalize_scalar(value: Any, max_chars: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    if isinstance(value, bytes):
        return _truncate_text(value.decode("utf-8", errors="replace"), max_chars)
    if isinstance(value, Exception):
        return _truncate_text("".join(traceback.format_exception_only(type(value), value)).strip(), max_chars)
    return _truncate_text(str(value), max_chars)


def redact_payload(payload: Any, *, max_field_chars: int | None = None) -> Any:
    """Return a redacted, JSON-friendly copy of payload.

    Sensitive keys are replaced with [REDACTED]. Strings are truncated
    according to AUDIT_MAX_FIELD_CHARS or max_field_chars.
    """
    limit = _max_field_chars() if max_field_chars is None else max_field_chars

    def _walk(value: Any, seen: set[int]) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return _truncate_text(value, limit)
        if isinstance(value, bytes):
            return _truncate_text(value.decode("utf-8", errors="replace"), limit)
        if isinstance(value, Exception):
            return _truncate_text("".join(traceback.format_exception_only(type(value), value)).strip(), limit)

        obj_id = id(value)
        if obj_id in seen:
            return "[Circular]"

        if isinstance(value, dict):
            seen.add(obj_id)
            try:
                redacted: dict[str, Any] = {}
                for key, item in value.items():
                    key_text = key if isinstance(key, str) else str(key)
                    if _is_sensitive_key(key_text):
                        redacted[key_text] = REDACTED_TEXT
                    else:
                        redacted[key_text] = _walk(item, seen)
                return redacted
            finally:
                seen.remove(obj_id)

        if isinstance(value, list):
            seen.add(obj_id)
            try:
                return [_walk(item, seen) for item in value]
            finally:
                seen.remove(obj_id)

        if isinstance(value, tuple):
            seen.add(obj_id)
            try:
                return tuple(_walk(item, seen) for item in value)
            finally:
                seen.remove(obj_id)

        if isinstance(value, set):
            seen.add(obj_id)
            try:
                return [_walk(item, seen) for item in sorted(value, key=lambda item: repr(item))]
            finally:
                seen.remove(obj_id)

        if hasattr(value, "__dict__") and not isinstance(value, type):
            seen.add(obj_id)
            try:
                return _walk(vars(value), seen)
            finally:
                seen.remove(obj_id)

        return _truncate_text(str(value), limit)

    return _walk(payload, set())


def _json_text(value: Any, *, max_field_chars: int | None = None) -> str | None:
    if value is None:
        return None
    redacted = redact_payload(value, max_field_chars=max_field_chars)
    try:
        return json.dumps(redacted, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception as exc:  # pragma: no cover - defensive fallback
        log.warning("Failed to JSON serialize audit payload: %s", exc, exc_info=True)
        return json.dumps(_truncate_text(str(redacted), max_field_chars or _max_field_chars()), ensure_ascii=False)


def _coerce_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        log.warning("audit field %s is not an int: %r", field_name, value)
        return None


def _coerce_text(value: Any, *, max_field_chars: int | None = None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Exception):
        return _normalize_scalar(value, max_field_chars or _max_field_chars())
    text = value if isinstance(value, str) else str(value)
    return _truncate_text(text, max_field_chars or _max_field_chars())


def init_audit_db(db_path: str | os.PathLike[str] | None = None) -> bool:
    """Create the audit table/indexes if needed.

    Returns True on success, False on warning/failure.
    """
    path = _shared_db_path(db_path)
    try:
        conn = _connect(path)
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        log.warning("Failed to initialize audit DB at %s: %s", path, exc, exc_info=True)
        return False


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
    """Write one audit row. Best-effort, never raises."""
    path = _shared_db_path(db_path)
    max_chars = _max_field_chars()
    try:
        init_audit_db(path)
        conn = _connect(path)
        try:
            payload_json = _json_text(payload, max_field_chars=max_chars)
            result_json = _json_text(result, max_field_chars=max_chars)
            error_text = _coerce_text(error, max_field_chars=max_chars)
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
                    chat_id, thread_id, message_id, payload_json, result_json, error,
                    duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    request_id or new_request_id(),
                    _coerce_text(actor_type, max_field_chars=max_chars),
                    _coerce_text(actor_id, max_field_chars=max_chars),
                    _coerce_text(action, max_field_chars=max_chars) or "",
                    _coerce_text(direction, max_field_chars=max_chars),
                    _coerce_text(source, max_field_chars=max_chars),
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
    """Async wrapper around log_event."""
    return await asyncio.to_thread(log_event, *args, **kwargs)
