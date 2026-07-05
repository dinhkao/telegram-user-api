"""Store: user-defined custom tasks on an order (add/remove definitions).

Transaction + IO only — pure rules live in order_store.domain. Custom tasks are
extra steps beside the 5 defaults; their DEFINITION (id+label) is stored in the
blob field `custom_tasks`, their done-status in `task_status[id]` (toggled via the
normal set_task_status path). Talks to shared app.db via order_store.schema.
"""
from __future__ import annotations

import logging
import time

from .schema import transaction
from .serialization import _save_order, get_order_by_thread_id
from .model import Order
from .domain import add_custom_task as _add, remove_custom_task as _remove, next_custom_task_id

log = logging.getLogger("order_db")

MAX_LABEL_LEN = 60


def add_custom_task(conn, thread_id: int, label: str, user_id: int | None) -> str | None:
    """Add a custom task; returns its generated id, or None on bad input / missing order."""
    label = (label or "").strip()[:MAX_LABEL_LEN]
    if not label:
        return None
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("add_custom_task: order not found thread=%s", thread_id)
            return None
        order = Order.from_dict(data)
        task_id = next_custom_task_id(order)
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        _add(order, task_id, label, user_id, now_iso)
        if _save_order(conn, thread_id, order.to_dict()):
            return task_id
        return None


def remove_custom_task(conn, thread_id: int, task_id: str) -> bool:
    """Remove a custom task definition + its status. Returns True on success."""
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("remove_custom_task: order not found thread=%s", thread_id)
            return False
        order = _remove(Order.from_dict(data), task_id)
        return _save_order(conn, thread_id, order.to_dict())
