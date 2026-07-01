"""Pure order-domain logic — no IO, no DB, no Telegram.

Operates on an `order_store.model.Order` (typed handle on the JSON blob). This is
the layer that should hold business rules so they can be unit-tested without a
database or a Telegram client. Currently: task-status transitions, extracted
verbatim from the store so behavior is identical (guarded by
tests/test_order_store.py). Connects to: order_store.model, order_store.schema
(MIRROR_FIELDS constant); adopted by order_store.tasks.
"""
from __future__ import annotations

from .model import Order
from .schema import MIRROR_FIELDS

REQUIRED_STEPS = ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]


def all_steps_done(task_status: dict) -> bool:
    return all(
        task_status.get(step, {}).get("done") or task_status.get(step, {}).get("skip", False)
        for step in REQUIRED_STEPS
    )


def mark_task(order: Order, task_type: str, user_id: int | None, *, done: bool, skip: bool, note: str, now_iso: str) -> Order:
    """Set task_type's status on the order (+ mirror field, all-done flag,
    flow_version). Mutates and returns the same Order. Pure."""
    payload = {"done": done, "by": user_id, "at": now_iso, "skip": skip}
    if note:
        payload["note"] = note
    task_status = order.task_status
    task_status[task_type] = payload
    order.set_field("task_status", task_status)
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        order.set_field(mirror_field, bool(done or skip))
    if all_steps_done(task_status):
        order.set_field("done_after_20250124", True)
    if "flow_version" not in order.data:
        order.set_field("flow_version", 2)
    return order


def clear_task(order: Order, task_type: str) -> Order:
    """Remove task_type from the order (+ unset mirror field). Mutates and
    returns the same Order. Pure."""
    task_status = order.task_status
    if task_type in task_status:
        del task_status[task_type]
    if task_status:
        order.set_field("task_status", task_status)
    else:
        order.del_field("task_status")
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        order.set_field(mirror_field, False)
    return order
