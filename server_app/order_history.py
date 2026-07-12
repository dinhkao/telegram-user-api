"""Lịch sử thao tác đầy đủ của một đơn từ ``audit_events``.

Nguồn gồm request web, thao tác Telegram và event nghiệp vụ (ảnh, kho, thanh
toán gộp...). Chỉ loại request đọc dữ liệu; mutation không có nhãn riêng vẫn
được hiện bằng nhãn dự phòng để hành động mới không âm thầm biến mất.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from aiohttp import web

from order_db import _get_connection

_ID = re.compile(r"/api/order/-?\d+")
_IMAGE_ID = re.compile(r"(/images)/\d+")
_COMMENT_ID = re.compile(r"(/comments)/\d+")
# actor_id kiểu địa chỉ (loopback proxy Tailscale serve / IP) = việc gọi nội bộ,
# không phải người dùng đăng nhập → hiển thị "Hệ thống".
_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
_IPISH = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$|^[0-9a-f:]+$", re.I)


def _load_names() -> dict:
    """username → display_name (để lịch sử hiện 'Duy' thay vì 'duy')."""
    names = {}
    try:
        from user_store import list_users
        names.update({str(u["username"]): (u.get("display_name") or u["username"]) for u in list_users()})
    except Exception:
        pass
    try:
        from bot_core.config import USER_NAMES
        names.update({str(k): v for k, v in USER_NAMES.items()})
    except Exception:
        pass
    return names


def _actor_display(actor_id, names: dict) -> str:
    """actor_id (web_user username / IP) → tên hiển thị cho lịch sử."""
    s = "" if actor_id is None else str(actor_id)
    if s in _LOOPBACK or _IPISH.match(s):
        return "Hệ thống"
    return names.get(s, s)


def _norm(path: str) -> str:
    path = _ID.sub("/api/order/{id}", path)
    path = _IMAGE_ID.sub(r"\1/{image_id}", path)
    return _COMMENT_ID.sub(r"\1/{comment_id}", path)


# path (đã chuẩn hoá) → nhãn. Path mutation mới chưa có trong đây vẫn hiện với
# nhãn dự phòng, tránh tình trạng backend đã audit nhưng UI lịch sử lại lọc mất.
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
    "/api/order/ngay-giao": "Đặt ngày giao",
    "/api/order/no-track": "Bỏ theo dõi nợ",
    "/api/order/bypass-debt": "Ẩn/hiện đơn khi thu tiền",
    "/api/order/reply": "Trả lời topic",
    "/api/order/print-giao": "In hoá đơn + phiếu giao",
    "/api/order/{id}/comments": "Bình luận",
    "/api/order/{id}/custom-task": "Thêm việc tùy chỉnh",
    "/api/order/{id}/custom-task/remove": "Xóa việc tùy chỉnh",
    "/api/order/{id}/allocate": "Xuất kho cho đơn",
    "/api/order/{id}/release": "Thu hồi hàng về kho",
    "/api/order/{id}/stock-confirm": "Chốt xuất kho",
    "/api/order/{id}/images/{image_id}/kind": "Đổi loại ảnh",
    "/api/order/{id}/images/{image_id}/comments": "Bình luận ảnh",
    "/api/order/{id}/images/{image_id}/comments/{comment_id}": "Xóa bình luận ảnh",
    "/api/order/{id}/invoice-image/ensure": "Tạo ảnh hóa đơn",
    "/api/order/{id}": "Xóa đơn",
}

_EVENT_LABELS = {
    "order.created": "Tạo đơn",
    "order.image_added": "Thêm ảnh",
    "order.image_deleted": "Xóa ảnh",
    "order.stock_allocated": "Xuất kho cho đơn",
    "order.stock_released": "Thu hồi hàng về kho",
    "order.stock_confirmed": "Chốt xuất kho",
    "order.stock_unconfirmed": "Bỏ chốt xuất kho",
    "order.bulk_payment": "Thu tiền gộp",
    "order.changed": "Cập nhật đơn",
}

# POST dùng để đọc/tính/xem trước, không phải một thao tác xảy ra với đơn.
_READ_ONLY_POSTS = {
    "/api/order/preview", "/api/order/totals", "/api/order/refresh-view",
    "/api/order/{id}/stock-pick/lock", "/api/order/{id}/stock-pick/unlock",
    "/api/order/{id}/invoice-edit/lock", "/api/order/{id}/invoice-edit/unlock",
}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_BUSINESS_EVENT_FOR_PATH = {
    "/api/order/{id}/allocate": "order.stock_allocated",
    "/api/order/{id}/release": "order.stock_released",
    "/api/order/{id}/stock-confirm": ("order.stock_confirmed", "order.stock_unconfirmed"),
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
        if norm == "/api/order/ngay-giao":
            return str(body.get("ngay_giao") or body.get("date") or "")
        if norm == "/api/order/bypass-debt":
            return "ẩn" if body.get("bypass", body.get("value", True)) else "hiện lại"
        if norm.endswith("/custom-task"):
            return str(body.get("label") or "")[:50]
        if norm.endswith("/stock-confirm"):
            return "chốt" if body.get("confirm") else "bỏ chốt"
        if norm.endswith("/kind"):
            return str(body.get("kind") or "")
    except Exception:
        pass
    return ""


def _event_detail(action: str, payload: dict) -> str:
    if payload.get("detail"):
        return str(payload["detail"])[:120]
    if action in ("order.stock_allocated", "order.stock_released"):
        boxes = payload.get("boxes") or []
        parts = [f"{b.get('box_code') or ('#' + str(b.get('box_id')))}: {b.get('taken', 0)}" for b in boxes]
        return ", ".join(parts)[:180]
    if action == "order.bulk_payment":
        try:
            return f"{int(payload.get('amount') or 0):,}đ".replace(",", ".")
        except (TypeError, ValueError):
            return ""
    return ""


def _epoch(value) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0


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
        "FROM audit_events WHERE thread_id = ? "
        "AND (scope = 'order' OR (scope IS NULL AND action LIKE 'order.%')) "
        "AND (action LIKE 'order.%' OR (action = 'http.request' AND "
        "(source LIKE 'POST %' OR source LIKE 'PUT %' OR source LIKE 'PATCH %' OR source LIKE 'DELETE %'))) "
        "ORDER BY id DESC LIMIT 300",
        (int(thread_id),),
    ).fetchall()
    names = _load_names()
    event_times: dict[str, list[float]] = {}
    for row in rows:
        action = row["action"] or ""
        if action != "http.request":
            event_times.setdefault(action, []).append(_epoch(row["ts"]))
    out = []
    for r in rows:
        action = r["action"] or ""
        if action != "http.request":
            label = _EVENT_LABELS.get(action)
            if not label:
                # Event order.* mới phải xuất hiện thay vì bị lọc âm thầm.
                label = "Cập nhật đơn"
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except Exception:
                payload = {}
            item = {
                "ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                "action": label, "detail": _event_detail(action, payload), "ok": True,
            }
            if action in ("order.image_added", "order.image_deleted"):
                item["image_id"] = payload.get("image_id")
            changes = payload.get("changes")
            if isinstance(changes, list):
                item["changes"] = changes
            out.append(item)
            if len(out) >= limit:
                break
            continue

        source = r["source"] or ""
        try:
            method, raw_path = source.split(" ", 1)
        except ValueError:
            continue
        method = method.upper()
        if method not in _WRITE_METHODS:
            continue
        norm = _norm(raw_path.split("?")[0])
        if norm in _READ_ONLY_POSTS:
            continue
        explicit = _BUSINESS_EVENT_FOR_PATH.get(norm)
        explicit_actions = explicit if isinstance(explicit, tuple) else (explicit,) if explicit else ()
        http_ts = _epoch(r["ts"])
        if any(abs(http_ts - event_ts) <= 10 for name in explicit_actions for event_ts in event_times.get(name, [])):
            continue
        # Upload/xóa ảnh có event tường minh kèm image_id ngay sau đó; bỏ request
        # HTTP tương ứng để lịch sử không hiện trùng hai dòng.
        if norm == "/api/order/{id}/images" or (method == "DELETE" and norm == "/api/order/{id}/images/{image_id}"):
            continue
        label = _LABELS.get(norm, "Cập nhật đơn")
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
