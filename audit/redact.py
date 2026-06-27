from __future__ import annotations

import traceback
from typing import Any

from .config import (
    COMPACT_SENSITIVE_KEY_HINTS,
    REDACTED_TEXT,
    SENSITIVE_KEY_HINTS,
    TRUNCATED_SUFFIX,
    max_field_chars as default_max_field_chars,
)


def _normalize_key(key: Any) -> str:
    if not isinstance(key, str):
        key = str(key)
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in key)


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    compact = "".join(ch for ch in normalized if ch.isalnum())
    hints = (hint.replace(" ", "_") for hint in SENSITIVE_KEY_HINTS)
    return any(hint in normalized for hint in hints) or any(hint in compact for hint in COMPACT_SENSITIVE_KEY_HINTS)


def _truncate_text(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[:max_chars] + TRUNCATED_SUFFIX


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
    limit = max_field_chars if max_field_chars is not None else default_max_field_chars()

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
                    redacted[key_text] = REDACTED_TEXT if _is_sensitive_key(key_text) else _walk(item, seen)
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
