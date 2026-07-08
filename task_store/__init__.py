"""task_store — hệ thống VIỆC (task list): bảng `tasks` trong app.db.

Việc tự do (free, link đơn tuỳ chọn) + MIRROR task của đơn (order_step /
order_custom — blob orders vẫn là nguồn sự thật, dual-write từ order_store).
API web: server_app/task_routes. UI: webapp #/viec.
"""
from .queries import (
    attach_order_text, counts, create_task, day_counts, day_tasks, get_task,
    list_tasks, open_counts_by_assignee, set_done, soft_delete, update_task,
)
from .mirror import (
    auto_assign_nop_tien, backfill_from_orders, mirror_order_tasks_safe, order_label_of, STEP_LABELS,
)

__all__ = [
    "attach_order_text", "counts", "create_task", "day_counts", "day_tasks",
    "get_task", "list_tasks", "open_counts_by_assignee", "set_done", "soft_delete", "update_task",
    "auto_assign_nop_tien", "backfill_from_orders", "mirror_order_tasks_safe", "order_label_of", "STEP_LABELS",
]
