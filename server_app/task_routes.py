"""API VIỆC (task list) — /api/tasks*: list/counts/create/update/done/delete +
lịch (?days=1 đếm theo hạn, ?day= chi tiết ngày).

Việc mirror từ đơn (order_step/order_custom): đánh dấu XONG ở đây được GHI
NGƯỢC về blob đơn qua api_task_handler_impl (nguồn sự thật) — hook store sẽ
mirror lại row này (vòng kín). Việc free: bảng tasks là nguồn sự thật.
Backfill mirror 1 lần mỗi process khi đụng API lần đầu.
Nối: task_store, order_api_tasks, web_auth (apply_web_actor), realtime.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiohttp import web

from server_app.order_api_common import apply_web_actor

log = logging.getLogger("task_routes")

_backfilled = False


def _today_vn() -> str:
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


async def _ensure_backfill():
    global _backfilled
    if _backfilled:
        return
    _backfilled = True
    from task_store import backfill_from_orders
    try:
        await asyncio.to_thread(backfill_from_orders)
    except Exception as e:  # noqa: BLE001
        log.warning("backfill tasks lỗi: %s", e)


def _me(request: web.Request) -> str:
    # web_auth tắt (mặc định, Tailscale-only) → server không biết user từ token;
    # client gửi kèm ?me=<username> làm fallback (chỉ để lọc/đếm 'Của tôi')
    return str(request.get("web_user") or request.query.get("me") or "")


def _emit():
    try:
        from server_app.realtime import emit_tasks_changed
        emit_tasks_changed()
    except Exception:  # noqa: BLE001
        pass


async def task_assignees_handler(request: web.Request):
    """Danh sách user để PHÂN CÔNG (username + tên + số việc chưa xong) — không cần admin."""
    def _run():
        from task_store import open_counts_by_assignee
        from user_store import list_users
        cnt = open_counts_by_assignee()
        return [{"username": u["username"], "display_name": u.get("display_name") or u["username"],
                 "open": cnt.get(u["username"], 0)}
                for u in list_users() if not u.get("disabled")]
    try:
        users = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        log.warning("assignees lỗi: %s", e)
        users = []
    return web.json_response({"ok": True, "users": users})


async def tasks_list_handler(request: web.Request):
    await _ensure_backfill()
    from task_store import attach_order_text, counts, day_counts, day_tasks, list_tasks
    q = request.query
    if q.get("counts"):
        from task_store import counts as _counts
        return web.json_response({"ok": True, "counts": await asyncio.to_thread(_counts, _me(request), _today_vn())})
    if q.get("days"):
        return web.json_response({"ok": True, "days": await asyncio.to_thread(day_counts)})
    if q.get("day"):
        items = await asyncio.to_thread(lambda: attach_order_text(day_tasks(q["day"].strip())))
        return web.json_response({"ok": True, "tasks": items})
    try:
        page = max(1, int(q.get("page", "1")))
    except ValueError:
        page = 1
    flt = (q.get("filter") or "open").strip()
    me = _me(request)
    today = _today_vn()

    def _run():
        items, total = list_tasks(flt=flt, assignee=(q.get("assignee") or "").strip(),
                                  me=me, page=page, today=today, q=(q.get("q") or "").strip())
        return attach_order_text(items), total, counts(me, today)

    items, total, cnt = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "tasks": items, "total": total, "page": page,
                              "total_pages": max(1, -(-total // 30)), "counts": cnt, "today": today})


async def tasks_create_handler(request: web.Request):
    await _ensure_backfill()
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    title = (body.get("title") or "").strip()
    if not title:
        return web.json_response({"ok": False, "error": "Thiếu tiêu đề việc"}, status=400)
    thread_id = body.get("thread_id")
    order_label = ""
    if thread_id:
        from server_app.orders_db import get_orders_conn
        from order_db import get_order_by_thread_id
        from task_store import order_label_of

        def _lbl():
            conn = get_orders_conn()
            try:
                d = get_order_by_thread_id(conn, int(thread_id))
                return order_label_of(d) if d else ""
            finally:
                conn.close()
        order_label = await asyncio.to_thread(_lbl)
        if not order_label:
            return web.json_response({"ok": False, "error": "Không tìm thấy đơn để link"}, status=404)
    from task_store import create_task
    task = await asyncio.to_thread(
        create_task, title=title, note=(body.get("note") or "").strip(),
        assignee=(body.get("assignee") or "").strip(), due_at=(body.get("due_at") or "").strip() or None,
        thread_id=int(thread_id) if thread_id else None, order_label=order_label,
        created_by=_me(request))
    _emit()
    # phân công cho người khác → báo đẩy
    if task.get("assignee") and task["assignee"] != _me(request):
        try:
            from server_app.notify import push_bg
            push_bg("📋 Việc mới", f"{_me(request) or '?'} giao việc: {title}",
                    {"type": "task", "task_id": str(task["id"])})
        except Exception:  # noqa: BLE001
            pass
    return web.json_response({"ok": True, "task": task})


async def task_update_handler(request: web.Request):
    """POST /api/tasks/{id} — sửa trường / done. Việc mirror: done ghi ngược về blob đơn."""
    await _ensure_backfill()
    try:
        task_id = int(request.match_info["task_id"])
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid"}, status=400)
    from task_store import get_task, set_done, update_task
    task = await asyncio.to_thread(get_task, task_id)
    if not task or task.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy việc"}, status=404)

    if "done" in body:
        done = bool(body.get("done"))
        if task["kind"] in ("order_step", "order_custom"):
            # ghi về NGUỒN SỰ THẬT (blob đơn) — dùng đúng flow /api/order/task
            # (cờ legacy, reminder, notify topic, refresh, realtime, mirror lại)
            from server_app.order_api_tasks import api_task_handler_impl
            from server_app.order_api_common import is_admin_request
            fwd = {"thread_id": task["thread_id"], "type": task["step_key"], "done": done}
            apply_web_actor(request, fwd)
            resp = await api_task_handler_impl(fwd, await is_admin_request(request))
            if getattr(resp, "status", 200) != 200:
                return resp
            task = await asyncio.to_thread(get_task, task_id)
        else:
            task = await asyncio.to_thread(set_done, task_id, done, _me(request))
        _emit()
        return web.json_response({"ok": True, "task": task})

    fields = {k: (body.get(k) or "").strip() for k in ("title", "note", "assignee") if k in body}
    if "due_at" in body:
        fields["due_at"] = (body.get("due_at") or "").strip() or None
    if task["kind"] != "free":
        # việc mirror: chỉ cho phân công + hạn + ghi chú (title/label thuộc về đơn)
        fields.pop("title", None)
    if "title" in fields and not fields["title"]:
        return web.json_response({"ok": False, "error": "Tiêu đề không được rỗng"}, status=400)
    task = await asyncio.to_thread(update_task, task_id, fields)
    _emit()
    return web.json_response({"ok": True, "task": task})


async def task_delete_handler(request: web.Request):
    """DELETE /api/tasks/{id} — chỉ việc FREE (việc từ đơn xoá ở trong đơn)."""
    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    from task_store import get_task, soft_delete
    task = await asyncio.to_thread(get_task, task_id)
    if not task or task.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy việc"}, status=404)
    if task["kind"] != "free":
        return web.json_response({"ok": False, "error": "Việc của đơn — gỡ trong trang đơn"}, status=400)
    await asyncio.to_thread(soft_delete, task_id)
    _emit()
    return web.json_response({"ok": True})


async def task_get_handler(request: web.Request):
    await _ensure_backfill()
    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    from task_store import attach_order_text, get_task

    def _run():
        t = get_task(task_id)
        return attach_order_text([t])[0] if t else None

    task = await asyncio.to_thread(_run)
    if not task or task.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy việc"}, status=404)
    return web.json_response({"ok": True, "task": task})
