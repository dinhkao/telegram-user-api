"""DDL bảng KHU VỰC XƯỞNG + BÁO CÁO VỆ SINH (app.db) — ensure per-module (như
disposal_store.ensure_table): CREATE TABLE IF NOT EXISTS + PRAGMA check, gọi từ
route handler chứ KHÔNG qua db_migrate. Dùng bởi area_store.queries/reports.
"""
from __future__ import annotations

_CREATE_AREAS = """
CREATE TABLE IF NOT EXISTS workshop_areas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

_CREATE_REPORTS = """
CREATE TABLE IF NOT EXISTS area_hygiene_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id    INTEGER NOT NULL,
    ymd        TEXT NOT NULL,
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
)
"""

# 1 khu vực chỉ 1 báo cáo CÒN SỐNG mỗi ngày (xoá mềm cũ thì tạo lại được).
_UX_DAY = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_area_report_day "
    "ON area_hygiene_reports(area_id, ymd) WHERE deleted_at IS NULL"
)
_IDX_LOOKUP = (
    "CREATE INDEX IF NOT EXISTS idx_area_report_lookup "
    "ON area_hygiene_reports(area_id, ymd)"
)


def ensure_tables(conn) -> None:
    conn.execute(_CREATE_AREAS)
    conn.execute(_CREATE_REPORTS)
    conn.execute(_UX_DAY)
    conn.execute(_IDX_LOOKUP)
