"""order_db.py — Read/write order task_status in shared SQLite.

Shares the same database as final_telegram (app.db).
WAL mode write connection — concurrent reads with one writer.
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import time

log = logging.getLogger("order_db")

SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)

# Mirror fields map: task_type -> order root boolean field
MIRROR_FIELDS = {
    "soan_hang": "soan",
    "giao_hang": "giao",
    "nop_tien": "nop",
    "nhan_tien": "nhan",
}


def _get_connection():
    """Open a WAL write connection."""
    conn = sqlite3.connect(
        SHARED_DB_PATH,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def get_order_by_thread_id(conn, thread_id: int) -> dict | None:
    """Read full order JSON by thread_id. Returns None if not found."""
    row = conn.execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _get_order_firebase_key(conn, thread_id: int) -> str | None:
    """Get the firebase_key for an order by thread_id."""
    row = conn.execute(
        "SELECT firebase_key FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    return row["firebase_key"] if row else None


def _save_order(conn, thread_id: int, data: dict) -> bool:
    """Save order JSON back to SQLite. Returns True on success."""
    try:
        conn.execute(
            "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), thread_id),
        )
        return True
    except Exception as e:
        log.error("Failed to save order thread=%d: %s", thread_id, e)
        return False


def _all_steps_done(task_status: dict) -> bool:
    """Check if all 5 core steps are done or skipped."""
    required = ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]
    return all(
        task_status.get(step, {}).get("done") or task_status.get(step, {}).get("skip", False)
        for step in required
    )


def set_task_status(conn, thread_id: int, task_type: str, user_id: int | None, *, skip: bool = False, done: bool = True) -> bool:
    """Write task_status entry and mirror boolean. Returns True on success."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        log.warning("set_task_status: order not found thread=%d", thread_id)
        return False

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    payload = {"done": done, "by": user_id, "at": now_iso, "skip": skip}

    # Update task_status
    task_status = data.get("task_status") or {}
    task_status[task_type] = payload
    data["task_status"] = task_status

    # Update mirror boolean
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        data[mirror_field] = bool(done or skip)

    # Set done_after_20250124 when all 5 steps complete
    if _all_steps_done(task_status):
        data["done_after_20250124"] = True

    # Set flow_version
    if "flow_version" not in data:
        data["flow_version"] = 2

    return _save_order(conn, thread_id, data)


def clear_task_status(conn, thread_id: int, task_type: str, user_id: int | None) -> bool:
    """Remove a task_status entry (undo). Returns True on success."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        log.warning("clear_task_status: order not found thread=%d", thread_id)
        return False

    task_status = data.get("task_status") or {}
    if task_type in task_status:
        del task_status[task_type]

    if task_status:
        data["task_status"] = task_status
    elif "task_status" in data:
        del data["task_status"]

    # Reset mirror boolean
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        data[mirror_field] = False

    return _save_order(conn, thread_id, data)
