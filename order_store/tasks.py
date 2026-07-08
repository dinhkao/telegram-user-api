from __future__ import annotations
import json
import logging
import time

from .schema import transaction
from .serialization import _save_order, get_order_by_thread_id
from .model import Order
from .domain import all_steps_done, mark_task, clear_task

log = logging.getLogger("order_db")

# Back-compat alias — some callers/tests import _all_steps_done from here.
_all_steps_done = all_steps_done


# Reference implementation of the 3-layer pattern (Phase 2, see docs/senior-review.md):
#   store (this fn): transaction + IO   ->   model: Order façade   ->   domain: pure rule
# Behavior is identical to the old inline version (guarded by tests/test_order_store.py).
def set_task_status(conn, thread_id: int, task_type: str, user_id: int | None, *, skip: bool = False, done: bool = True, note: str = "") -> bool:
    # Atomic read-modify-write: take the write lock before the SELECT so a
    # concurrent writer cannot interleave and clobber the blob.
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("set_task_status: order not found thread=%d", thread_id)
            return False
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        order = mark_task(Order.from_dict(data), task_type, user_id, done=done, skip=skip, note=note, now_iso=now_iso)
        d = order.to_dict()
        ok = _save_order(conn, thread_id, d)
    # MIRROR sang bảng tasks (task list) — best-effort, NGOÀI transaction
    from task_store import mirror_order_tasks_safe
    mirror_order_tasks_safe(thread_id, d)
    return ok


def clear_task_status(conn, thread_id: int, task_type: str, user_id: int | None) -> bool:
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("clear_task_status: order not found thread=%d", thread_id)
            return False
        order = clear_task(Order.from_dict(data), task_type)
        d = order.to_dict()
        ok = _save_order(conn, thread_id, d)
    from task_store import mirror_order_tasks_safe
    mirror_order_tasks_safe(thread_id, d)
    return ok


def get_all_tasks(conn) -> list[dict]:
    tasks = []
    for row in conn.execute("SELECT thread_id, firebase_key, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"):
        try:
            order = json.loads(row["json"])
            ts = order.get("task_status", {})
            if ts:
                tasks.append({"thread_id": row["thread_id"], "firebase_key": row["firebase_key"], "task_status": ts, "name": order.get("khach_hang", order.get("name", "")), "flow_version": order.get("flow_version")})
        except json.JSONDecodeError:
            continue
    return tasks


def sort_tasks(conn) -> tuple[int, str]:
    tasks = get_all_tasks(conn)
    return len(tasks), f"✅ Đã sắp xếp {len(tasks)} task"
