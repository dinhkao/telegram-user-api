"""Đơn MỚI (chưa ai bấm bước nào) phải có đủ 5 dòng mirror trong web_tasks — đường
tạo đơn gọi mirror ngay (channel_handlers/create.py), không chờ set_task_status/backfill."""
import os
import tempfile

import pytest

import task_store.schema as TS
from task_store import mirror_order_tasks_safe, STEP_LABELS
from utils.db import get_connection


@pytest.fixture
def tasks_db(monkeypatch):
    db = os.path.join(tempfile.mkdtemp(), "app.db")
    monkeypatch.setattr(TS, "get_connection", lambda *a, **k: get_connection(db))
    monkeypatch.setattr(TS, "_ensured", False)
    return db


def test_fresh_order_blob_mirrors_five_pending_steps(tasks_db):
    from channel_handlers.config import build_new_order
    blob = build_new_order("Lp\n2 t 10 m", "Lp\n2 t 10 m", 518958, "fk1", 38428)
    assert set(blob["task_status"]) >= set(STEP_LABELS)
    mirror_order_tasks_safe(518958, blob)
    conn = get_connection(tasks_db)
    rows = conn.execute(
        "SELECT step_key, done, deleted_at FROM web_tasks WHERE kind='order_step' AND thread_id=518958"
    ).fetchall()
    conn.close()
    assert sorted(r["step_key"] for r in rows) == sorted(STEP_LABELS)
    assert all(r["done"] == 0 and r["deleted_at"] is None for r in rows)


def test_create_path_calls_mirror():
    src = open("channel_handlers/create.py", encoding="utf-8").read()
    assert "mirror_order_tasks_safe(thread_id, new_order)" in src
