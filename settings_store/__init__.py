"""Cài đặt hệ thống (app settings) — blob JSON trong kv_store['app_settings'] (app.db).

Toggle hành vi bật/tắt được từ webapp (trang Cài đặt, admin). Đọc qua get_bool
(có default nên thiếu key = hành vi mặc định). Nối: utils.db.
"""
from __future__ import annotations

import json
import time

from utils.db import get_connection

_KV_PATH = "app_settings"


def _ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv_store (path TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)"
    )


def get_all(conn=None) -> dict:
    """Toàn bộ cài đặt (dict). conn=None tự mở/đóng."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        _ensure(conn)
        row = conn.execute("SELECT value FROM kv_store WHERE path = ?", (_KV_PATH,)).fetchone()
        if not row or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    finally:
        if own:
            conn.close()


def get_bool(key: str, default: bool, conn=None) -> bool:
    v = get_all(conn).get(key)
    return default if v is None else bool(v)


def set_value(key: str, value, conn=None) -> dict:
    """Ghi 1 key (upsert blob), trả toàn bộ settings mới."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        _ensure(conn)
        data = get_all(conn)
        data[key] = value
        conn.execute(
            "INSERT INTO kv_store(path, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (_KV_PATH, json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
        )
        conn.commit()
        return data
    finally:
        if own:
            conn.close()
