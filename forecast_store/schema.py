"""DDL bảng DỰ BÁO HÀNG HOÁ (app.db) — ensure per-module (như area_store): gọi từ route /
CLI, KHÔNG qua db_migrate. `daily_forecasts` 1 dòng/ngày (ymd UNIQUE, đăng lại = đè);
`forecast_views` ai đã mở bản nào (popup "chưa xem" dựa vào đây).
Dùng bởi forecast_store.queries.
"""
from __future__ import annotations

_CREATE_FORECASTS = """
CREATE TABLE IF NOT EXISTS daily_forecasts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ymd        TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    summary    TEXT NOT NULL DEFAULT '',
    body_md    TEXT NOT NULL DEFAULT '',
    data_json  TEXT NOT NULL DEFAULT '{}',
    model      TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
)
"""

_CREATE_VIEWS = """
CREATE TABLE IF NOT EXISTS forecast_views (
    forecast_id INTEGER NOT NULL,
    username    TEXT NOT NULL,
    viewed_at   TEXT NOT NULL,
    PRIMARY KEY (forecast_id, username)
)
"""

# DDL chạy 1 lần mỗi FILE DB mỗi process — khoá theo ĐƯỜNG DẪN, KHÔNG phải id(conn):
# CPython tái dùng địa chỉ sau GC nên connection MỚI có thể trùng id của connection đã
# đóng → trượt DDL, DB mới không có bảng nào (suite đỏ ngẫu nhiên ở test_forecast_store
# khi thứ tự cấp phát đổi). Cùng cách làm với notif_store.fcm_tokens / user_store.schema.
_ensured: set[str] = set()


def _db_key(conn) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2] if row else "")
    except Exception:      # noqa: BLE001 — không đọc được thì cứ chạy DDL (idempotent)
        return ""


def ensure_tables(conn) -> None:
    key = _db_key(conn)
    if key and key in _ensured:
        return
    conn.execute(_CREATE_FORECASTS)
    conn.execute(_CREATE_VIEWS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_forecasts_ymd ON daily_forecasts(ymd DESC)")
    try:
        conn.commit()
    except Exception:  # noqa: BLE001 — autocommit conn
        pass
    if key:
        _ensured.add(key)
