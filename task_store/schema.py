"""Bảng `web_tasks` (app.db) — hệ thống VIỆC (task list) toàn cục.

(Tên web_tasks vì bảng `tasks` đã bị chiếm bởi sync Firebase đời cũ — 18k row
reminder legacy, không đụng.)

3 loại (kind):
  free         — việc tự tạo, có thể link đơn (thread_id) hoặc không
  order_step   — MIRROR 1 trong 5 bước workflow của đơn (blob vẫn là nguồn sự
                 thật; đổi ở blob → order_store hook đẩy sang đây — dual-write
                 như production_report_rows)
  order_custom — MIRROR việc tự thêm trong đơn (custom_tasks của blob)
Mirror định danh bằng UNIQUE(kind, thread_id, step_key) → upsert idempotent.
Nối: utils.db (cổng chung). Dùng bởi: task_store.queries/mirror, server_app/task_routes.
"""
from __future__ import annotations

from utils.db import get_connection

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS web_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'free',
    thread_id INTEGER,
    step_key TEXT,
    title TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    order_label TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    due_at TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_by TEXT,
    done_at INTEGER,
    created_by TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted_at INTEGER
)
"""
_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_mirror ON web_tasks(kind, thread_id, step_key) WHERE step_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tasks_open ON web_tasks(done, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON web_tasks(assignee, done)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_thread ON web_tasks(thread_id)",
)

COLS = ("id, kind, thread_id, step_key, title, note, order_label, assignee, due_at, "
        "done, done_by, done_at, created_by, created_at, updated_at, deleted_at")

_ensured = False


def conn_tasks():
    """Connection app.db + đảm bảo schema (DDL 1 lần mỗi process)."""
    global _ensured
    conn = get_connection()
    if not _ensured:
        conn.execute(_CREATE_SQL)
        for ddl in _INDEXES:
            conn.execute(ddl)
        _ensured = True
    return conn
