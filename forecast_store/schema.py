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

_ensured: set[int] = set()


def ensure_tables(conn) -> None:
    key = id(conn)
    if key in _ensured:
        return
    conn.execute(_CREATE_FORECASTS)
    conn.execute(_CREATE_VIEWS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_forecasts_ymd ON daily_forecasts(ymd DESC)")
    try:
        conn.commit()
    except Exception:  # noqa: BLE001 — autocommit conn
        pass
    _ensured.add(key)
