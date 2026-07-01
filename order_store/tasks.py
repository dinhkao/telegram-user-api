from __future__ import annotations
import json
import logging
import time

from .schema import MIRROR_FIELDS, transaction
from .serialization import _save_order, get_order_by_thread_id

log = logging.getLogger("order_db")


def _all_steps_done(task_status: dict) -> bool:
    required = ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]
    return all(task_status.get(step, {}).get("done") or task_status.get(step, {}).get("skip", False) for step in required)


def set_task_status(conn, thread_id: int, task_type: str, user_id: int | None, *, skip: bool = False, done: bool = True, note: str = "") -> bool:
    # Atomic read-modify-write: take the write lock before the SELECT so a
    # concurrent writer cannot interleave and clobber the blob.
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("set_task_status: order not found thread=%d", thread_id)
            return False
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        payload = {"done": done, "by": user_id, "at": now_iso, "skip": skip}
        if note:
            payload["note"] = note
        task_status = data.get("task_status") or {}
        task_status[task_type] = payload
        data["task_status"] = task_status
        mirror_field = MIRROR_FIELDS.get(task_type)
        if mirror_field:
            data[mirror_field] = bool(done or skip)
        if _all_steps_done(task_status):
            data["done_after_20250124"] = True
        if "flow_version" not in data:
            data["flow_version"] = 2
        return _save_order(conn, thread_id, data)


def clear_task_status(conn, thread_id: int, task_type: str, user_id: int | None) -> bool:
    with transaction(conn):
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
        mirror_field = MIRROR_FIELDS.get(task_type)
        if mirror_field:
            data[mirror_field] = False
        return _save_order(conn, thread_id, data)


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
