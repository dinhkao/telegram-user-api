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
    """actor_id (web_user username / Telegram id / IP) → tên hiển thị cho lịch sử.
    Tra tên TRƯỚC khi đoán IP — id Telegram toàn chữ số từng bị nuốt thành 'Hệ thống'."""
    s = "" if actor_id is None else str(actor_id)
    if s in names:
        return names[s]
    if s in _LOOPBACK or _IPISH.match(s):
        return "Hệ thống"
    return s


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
    "/api/order/invoice/reference-image": "Đổi ảnh tham chiếu HĐ",
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


def _fmt_ngay_giao(v: str) -> str:
    """'2026-07-14T08:30' → '14/07/2026 08:30' (đọc kiểu VN)."""
    try:
        dt = datetime.fromisoformat(str(v))
        hm = dt.strftime(" %H:%M") if (dt.hour or dt.minute) else ""
        return dt.strftime("%d/%m/%Y") + hm
    except (ValueError, TypeError):
        return str(v or "")


def _detail(norm: str, body: dict, resolver=None) -> tuple[str, list]:
    """(detail text, parts có link) cho 1 request ghi theo path chuẩn hoá."""
    from server_app.history_format import customer_part, money, part, parts_text
    try:
        if norm in ("/api/order/task", "/api/order/soan", "/api/order/ban", "/api/order/giao", "/api/order/nop-tien"):
            t = _TASK_VI.get(str(body.get("type", "")), body.get("type", "")) or norm.rsplit("/", 1)[-1]
            done = body.get("done", True)
            note = str(body.get("note") or "").strip()
            txt = f"{t}{'' if done is not False else ' (bỏ)'}" + (f" · “{note[:40]}”" if note and not note.startswith("imgs:") else "")
            return txt, [part(txt)]
        if norm.endswith("/task_status/clear"):
            txt = _TASK_VI.get(str(body.get("type", "")), str(body.get("type", "")))
            return txt, [part(txt)]
        if norm == "/api/order/payment/delete":
            txt = f"phiếu thu #{body.get('payment_id')}" if body.get("payment_id") is not None else ""
            return txt, [part(txt)] if txt else []
        if norm.startswith("/api/order/payment"):
            amt = body.get("amount")
            txt = money(amt) if str(amt or "").isdigit() else ""
            return txt, [part(txt)] if txt else []
        if norm in ("/api/order/fix", "/api/order/auto-parse", "/api/order/reply"):
            txt = " ".join(str(body.get("text") or "").split())[:60]
            return txt, [part(f"“{txt}”")] if txt else []
        if norm.endswith("/comments"):
            txt = (body.get("text") or "")[:60]
            return txt, [part(f"“{txt}”")] if txt else []
        if norm == "/api/order/assign-customer":
            key = body.get("customer_key")
            if key is None or str(key) == "":
                return "", []
            p = customer_part(key, resolver)
            return p["t"], [part("→ "), p]
        if norm == "/api/order/ngay-giao":
            raw = body.get("ngay_giao") or body.get("date")
            txt = _fmt_ngay_giao(raw) if raw else "bỏ hẹn"
            return txt, [part(txt)]
        if norm == "/api/order/no-track":
            txt = "bật (đơn không tính nợ nữa)" if body.get("on", True) else "tắt (tính nợ lại)"
            return txt, [part(txt)]
        if norm == "/api/order/bypass-debt":
            txt = "ẩn khỏi trang thu tiền" if body.get("bypass", body.get("value", body.get("on", True))) else "hiện lại ở trang thu tiền"
            return txt, [part(txt)]
        if norm.endswith("/custom-task"):
            txt = str(body.get("label") or "")[:50]
            return txt, [part(f"“{txt}”")] if txt else []
        if norm.endswith("/custom-task/remove"):
            txt = str(body.get("label") or body.get("id") or "")[:50]
            return str(txt), [part(str(txt))] if txt else []
        if norm.endswith("/stock-confirm"):
            txt = "chốt" if body.get("confirm") else "bỏ chốt"
            return txt, [part(txt)]
        if norm.endswith("/kind"):
            txt = str(body.get("kind") or "")
            return txt, [part(txt)]
    except Exception:
        pass
    return "", []


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
    from server_app.event_format import event_entry
    from server_app.history_format import Resolver, parts_text
    resolver = Resolver(conn)
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
            try:
                payload = json.loads(r["payload_json"] or "{}")
                payload = payload if isinstance(payload, dict) else {}
            except Exception:
                payload = {}
            ent = event_entry(action, payload, resolver)
            if ent:
                label, parts = ent
                # event Telegram cũ mang sẵn payload['detail'] → giữ làm chi tiết
                if not parts and payload.get("detail"):
                    parts = [{"t": str(payload["detail"])[:120]}]
            else:
                # Event order.* mới phải xuất hiện thay vì bị lọc âm thầm.
                label, parts = _EVENT_LABELS.get(action, "Cập nhật đơn"), []
            item = {
                "ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                "action": label, "detail": parts_text(parts), "parts": parts, "ok": True,
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
        detail, parts = _detail(norm, body, resolver)
        out.append({
            "ts": r["ts"], "actor": _actor_display(r["actor_id"], names), "action": label,
            "detail": detail, "parts": parts,
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
