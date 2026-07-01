from __future__ import annotations

import logging
import os

from utils.paths import DEFAULT_SHARED_DB as DEFAULT_SHARED_DB_PATH

log = logging.getLogger("audit_log")
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


def shared_db_path(db_path: str | os.PathLike[str] | None = None) -> str:
    path = os.fspath(db_path) if db_path is not None else os.getenv("SHARED_DB_PATH", DEFAULT_SHARED_DB_PATH)
    return os.path.expanduser(path)


def max_field_chars() -> int:
    raw = os.getenv("AUDIT_MAX_FIELD_CHARS")
    if not raw:
        return DEFAULT_MAX_FIELD_CHARS
    try:
        value = int(raw)
        return value if value > 0 else DEFAULT_MAX_FIELD_CHARS
    except (TypeError, ValueError):
        log.warning("AUDIT_MAX_FIELD_CHARS invalid=%r; using default %d", raw, DEFAULT_MAX_FIELD_CHARS)
        return DEFAULT_MAX_FIELD_CHARS

