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
from .domain import add_custom_task as _add, remove_custom_task as _remove, next_custom_task_id, missing_custom_labels

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


def apply_customer_default_tasks(conn, thread_id: int, firebase_key: str, user_id: int | None = None) -> list[str]:
    """Việc mặc định của khách (customer JSON `default_tasks`) → auto-thêm vào đơn
    (dưới 5 việc chuẩn, cùng cơ chế custom task). Bỏ label đã có trên đơn nên gán
    lại khách / parse lại KHÔNG nhân đôi. Gọi ở MỌI chỗ gán khách vào đơn
    (auto-parse, fix, web assign, lệnh Telegram). Trả list label vừa thêm."""
    from .customers import get_customer_by_key
    cust = get_customer_by_key(conn, str(firebase_key)) if firebase_key else None
    labels = [str(x).strip()[:MAX_LABEL_LEN] for x in ((cust or {}).get("default_tasks") or []) if str(x or "").strip()]
    if not labels:
        return []
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            return []
        order = Order.from_dict(data)
        todo = missing_custom_labels(order, labels)
        if not todo:
            return []
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        for lb in todo:
            _add(order, next_custom_task_id(order), lb, user_id, now_iso)
        if _save_order(conn, thread_id, order.to_dict()):
            log.info("customer default tasks: thread=%s +%d (%s)", thread_id, len(todo), ", ".join(todo))
            return todo
        return []


def remove_custom_task(conn, thread_id: int, task_id: str) -> bool:
    """Remove a custom task definition + its status. Returns True on success."""
    with transaction(conn):
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            log.warning("remove_custom_task: order not found thread=%s", thread_id)
            return False
        order = _remove(Order.from_dict(data), task_id)
        return _save_order(conn, thread_id, order.to_dict())
