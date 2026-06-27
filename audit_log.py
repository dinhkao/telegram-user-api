"""Compatibility wrapper for the audit package."""
from __future__ import annotations

import sqlite3

from audit import DEFAULT_MAX_FIELD_CHARS, DEFAULT_SHARED_DB_PATH, async_log_event, init_audit_db, log_event, new_request_id, redact_payload

__all__ = [
    "DEFAULT_SHARED_DB_PATH",
    "DEFAULT_MAX_FIELD_CHARS",
    "init_audit_db",
    "log_event",
    "async_log_event",
    "new_request_id",
    "redact_payload",
]

