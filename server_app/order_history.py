"""Lịch sử thao tác của 1 đơn — đọc từ audit_events (do audit_middleware ghi).

Middleware ghi mọi request kèm thread_id + actor (web user). Ở đây lọc các thao
tác THAY ĐỔI (POST) trên đơn, dịch path → nhãn tiếng Việt + trích chi tiết ngắn.
GET /api/order/{thread_id}/history dùng hàm get_order_history.
"""
from __future__ import annotations

import json
import re

from aiohttp import web

from order_db import _get_connection

_ID = re.compile(r"/api/order/-?\d+")
# actor_id kiểu địa chỉ (loopback proxy Tailscale serve / IP) = việc gọi nội bộ,
# không phải người dùng đăng nhập → hiển thị "Hệ thống".
_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
_IPISH = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$|^[0-9a-f:]+$", re.I)


def _load_names() -> dict:
    """username → display_name (để lịch sử hiện 'Duy' thay vì 'duy')."""
    try:
        from user_store import list_users
        return {u["username"]: (u.get("display_name") or u["username"]) for u in list_users()}
    except Exception:
        return {}


def _actor_display(actor_id, names: dict) -> str:
    """actor_id (web_user username / IP) → tên hiển thị cho lịch sử."""
    s = "" if actor_id is None else str(actor_id)
    if s in _LOOPBACK or _IPISH.match(s):
        return "Hệ thống"
    return names.get(s, s)


def _norm(path: str) -> str:
    return _ID.sub("/api/order/{id}", path)


# path (đã chuẩn hoá) → nhãn. Chỉ path có trong đây mới vào lịch sử.
_LABELS = {
    "/api/order/create": "Tạo đơn",
    "/api/order/task": "Công việc",
    "/api/order/soan": "Đánh dấu soạn",
    "/api/order/ban": "Đánh dấu bán HĐ",
    "/api/order/giao": "Đánh dấu giao",
    "/api/order/nop-tien": "Đánh dấu nộp tiền",
    "/api/order/{id}/task_status/clear": "Bỏ đánh dấu",
    "/api/order/invoice/create-kiotviet": "Tạo hoá đơn KiotViet",
    "/api/order/invoice/delete-kiotviet": "Xoá hoá đơn KiotViet",
    "/api/order/invoice/update": "Sửa hoá đơn",
    "/api/order/payment/tm": "Thu tiền mặt",
    "/api/order/payment/ck": "Thu chuyển khoản",
    "/api/order/payment/delete": "Xóa thanh toán",
    "/api/order/auto-parse": "Tự phân tích lại",
    "/api/order/assign-customer": "Gán khách hàng",
    "/api/order/refresh-debt": "Cập nhật nợ KiotViet",
    "/api/order/fix": "Sửa nội dung đơn",
    "/api/order/reply": "Trả lời topic",
    "/api/order/print-giao": "In hoá đơn + phiếu giao",
    "/api/order/{id}/comments": "Bình luận",
}

_TASK_VI = {"soan_hang": "soạn hàng", "ban_hd": "bán HĐ", "giao_hang": "giao hàng",
            "nop_tien": "nộp tiền", "nhan_tien": "nhận tiền",
            "soan": "soạn hàng", "ban": "bán HĐ", "giao": "giao hàng", "nop": "nộp tiền"}


def _detail(norm: str, body: dict) -> str:
    try:
        if norm in ("/api/order/task", "/api/order/soan", "/api/order/ban", "/api/order/giao", "/api/order/nop-tien"):
            t = _TASK_VI.get(str(body.get("type", "")), body.get("type", "")) or norm.rsplit("/", 1)[-1]
            done = body.get("done", True)
            return f"{t}{'' if done is not False else ' (bỏ)'}"
        if norm.endswith("/task_status/clear"):
            return _TASK_VI.get(str(body.get("type", "")), str(body.get("type", "")))
        if norm.startswith("/api/order/payment"):
            amt = body.get("amount")
            return f"{int(amt):,}đ".replace(",", ".") if str(amt).isdigit() else ""
        if norm == "/api/order/fix":
            return (body.get("text") or "")[:50]
        if norm.endswith("/comments"):
            return (body.get("text") or "")[:50]
        if norm == "/api/order/assign-customer":
            return str(body.get("customer_key") or "")
    except Exception:
        pass
    return ""


def get_order_history(thread_id, limit: int = 60) -> list[dict]:
    conn = _get_connection()
    try:
        return _get_order_history_rows(conn, thread_id, limit)
    except Exception:
        return []
    finally:
        conn.close()


def _get_order_history_rows(conn, thread_id, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, actor_id, actor_type, action, source, payload_json, result_json "
        "FROM audit_events WHERE thread_id = ? AND action IN ('http.request', 'order.image_added') "
        "ORDER BY id DESC LIMIT 300",
        (int(thread_id),),
    ).fetchall()
    names = _load_names()
    out = []
    for r in rows:
        # Thêm ảnh (ghi tường minh vì upload là multipart, id ảnh không nằm trong request)
        if r["action"] == "order.image_added":
            try:
                pid = json.loads(r["payload_json"] or "{}").get("image_id")
            except Exception:
                pid = None
            out.append({"ts": r["ts"], "actor": _actor_display(r["actor_id"], names), "action": "Thêm ảnh",
                        "detail": "", "image_id": pid, "ok": True})
            if len(out) >= limit:
                break
            continue
        source = r["source"] or ""
        if not source.startswith("POST "):
            continue
        norm = _norm(source[5:].split("?")[0])
        label = _LABELS.get(norm)
        if not label:
            continue
        body = {}
        changes = []
        try:
            payload = json.loads(r["payload_json"] or "{}")
            b = payload.get("body")
            if isinstance(b, str) and b.strip().startswith("{"):
                body = json.loads(b)
            ch = payload.get("changes")
            if isinstance(ch, list):
                changes = ch
        except Exception:
            body, changes = {}, []
        status = None
        try:
            status = json.loads(r["result_json"] or "{}").get("status")
        except Exception:
            status = None
        out.append({
            "ts": r["ts"], "actor": _actor_display(r["actor_id"], names), "action": label,
            "detail": _detail(norm, body),
            "changes": changes,
            "ok": status is None or (isinstance(status, int) and 200 <= status < 300),
        })
        if len(out) >= limit:
            break
    return out


async def order_history_handler(request: web.Request):
    thread_id = request.match_info.get("thread_id", "").strip()
    if not thread_id.lstrip("-").isdigit():
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    import asyncio
    history = await asyncio.to_thread(get_order_history, int(thread_id))
    return web.json_response({"ok": True, "history": history})
