from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from .config import log, max_field_chars as default_max_field_chars, shared_db_path
from .redact import _normalize_scalar, _truncate_text, redact_payload

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    request_id TEXT,
    actor_type TEXT,
    actor_id TEXT,
    action TEXT NOT NULL,
    direction TEXT,
    source TEXT,
    scope TEXT,
    chat_id INTEGER,
    thread_id INTEGER,
    message_id INTEGER,
    payload_json TEXT,
    result_json TEXT,
    error TEXT,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts);
CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_thread_id ON audit_events(thread_id);
"""


def _connect(db_path: str):
    from utils.db import get_connection
    return get_connection(db_path, autocommit=True, busy_timeout=5000)


def _json_text(value: Any, *, max_field_chars: int | None = None) -> str | None:
    if value is None:
        return None
    limit = max_field_chars if max_field_chars is not None else default_max_field_chars()
    redacted = redact_payload(value, max_field_chars=limit)
    try:
        return json.dumps(redacted, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return json.dumps(_truncate_text(str(redacted), limit), ensure_ascii=False)


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
    limit = max_field_chars if max_field_chars is not None else default_max_field_chars()
    return _normalize_scalar(value, limit)


def init_audit_db(db_path: str | os.PathLike[str] | None = None) -> bool:
    from utils.db import IS_POSTGRES
    if IS_POSTGRES:
        return True  # audit_events do migrations/pg/0001_init.sql tạo — không chạy DDL SQLite.
    path = shared_db_path(db_path)
    try:
        conn = _connect(path)
        try:
            conn.executescript(_SCHEMA_SQL)
            # Migration DB cũ: thêm cột scope nếu chưa có (phân biệt order/production/box).
            # Index scope tạo SAU (không để trong _SCHEMA_SQL vì bảng cũ chưa có cột scope
            # → executescript sẽ lỗi trước khi kịp ALTER).
            cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_events)").fetchall()}
            if "scope" not in cols:
                conn.execute("ALTER TABLE audit_events ADD COLUMN scope TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_scope_thread ON audit_events(scope, thread_id)")
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        log.warning("Failed to initialize audit DB at %s", path, exc_info=True)
        return False
