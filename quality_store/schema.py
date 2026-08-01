"""DDL bảng BÁO CÁO CHẤT LƯỢNG MÂM KẸO (`tray_quality_reports`, app.db) — ensure
per-module (như area_store.schema): CREATE TABLE IF NOT EXISTS, gọi từ route handler
chứ KHÔNG qua db_migrate. Thợ dùng bảng có sẵn `production_workers` (worker_store),
ở đây chỉ có bảng báo cáo. Dùng bởi quality_store.reports.
"""
from __future__ import annotations

_CREATE_REPORTS = """
CREATE TABLE IF NOT EXISTS tray_quality_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id  INTEGER NOT NULL,
    ymd        TEXT NOT NULL,
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

# 1 thợ chỉ 1 báo cáo CÒN SỐNG mỗi ngày (xoá mềm cũ thì chụp lại được cùng ngày).
_UX_DAY = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_tray_quality_day "
    "ON tray_quality_reports(worker_id, ymd) WHERE deleted_at IS NULL"
)
_IDX_LOOKUP = (
    "CREATE INDEX IF NOT EXISTS idx_tray_quality_lookup "
    "ON tray_quality_reports(worker_id, ymd)"
)


def ensure_tables(conn) -> None:
    conn.execute(_CREATE_REPORTS)
    conn.execute(_UX_DAY)
    conn.execute(_IDX_LOOKUP)
