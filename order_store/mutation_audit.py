"""Audit tại choke point lưu order blob.

Mọi đường web/Telegram/background cuối cùng đều đi qua ``_save_order`` hoặc
``_update_order_json_field``. Ghi bằng chính connection hiện tại để event và
mutation cùng transaction, không bị SQLite lock do mở connection thứ hai.
"""
from __future__ import annotations

import contextvars
import json
import uuid
from datetime import UTC, datetime

_actor_ctx: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar(
    "order_audit_actor", default=("system", "Hệ thống")
)


def set_actor(actor_type: str, actor_id) -> contextvars.Token:
    return _actor_ctx.set((str(actor_type or "system"), str(actor_id or "Hệ thống")))


def reset_actor(token: contextvars.Token) -> None:
    _actor_ctx.reset(token)


def _infer_actor(after: dict, changes: list[dict]) -> tuple[str, str]:
    actor_type, actor_id = _actor_ctx.get()
    if actor_type != "system" or actor_id != "Hệ thống":
        return actor_type, actor_id
    # Telegram task mutations lưu user id ngay trong task_status.
    changed_labels = {str(c.get("label") or "").casefold() for c in changes}
    task_labels = {"soạn hàng", "bán hóa đơn", "giao hàng", "nộp tiền", "nhận tiền"}
    if changed_labels & task_labels:
        statuses = [s for s in (after.get("task_status") or {}).values() if isinstance(s, dict) and s.get("by")]
        if statuses:
            newest = max(statuses, key=lambda s: str(s.get("at") or ""))
            return "telegram", str(newest["by"])
    # Payment record cũng mang người tạo; dùng dòng mới nhất làm fallback.
    payments = after.get("payments") or []
    if payments and isinstance(payments[-1], dict):
        by = payments[-1].get("created_by") or payments[-1].get("user")
        if by:
            return "telegram", str(by)
    return actor_type, actor_id


def record_order_change(conn, thread_id: int, before: dict | None, after: dict | None) -> None:
    before, after = before or {}, after or {}
    before_cmp, after_cmp = dict(before), dict(after)
    before_cmp.pop("updated_at", None)
    after_cmp.pop("updated_at", None)
    if before_cmp == after_cmp:
        return
    try:
        from server_app.order_diff import diff_changes
        changes = diff_changes(before_cmp, after_cmp)
        if not changes:
            changes = [{"label": "Dữ liệu đơn hàng", "old": "", "new": "Đã cập nhật"}]
        actor_type, actor_id = _infer_actor(after, changes)
        # Web đã được audit_middleware ghi kèm path/chi tiết/status; không ghi
        # thêm event choke-point để tránh hai dòng cho cùng một cú bấm.
        if actor_type in {"web_user", "http_client"}:
            return
        conn.execute(
            """INSERT INTO audit_events (
                ts, request_id, actor_type, actor_id, action, source, scope,
                thread_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(UTC).isoformat(), str(uuid.uuid4()), actor_type, actor_id,
                "order.changed", "order_store", "order", int(thread_id),
                json.dumps({"changes": changes}, ensure_ascii=False),
            ),
        )
    except Exception:
        # DB test cũ có thể chưa tạo audit_events; audit là best-effort và tuyệt
        # đối không được làm hỏng thao tác nghiệp vụ.
        return
