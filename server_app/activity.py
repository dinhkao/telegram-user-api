"""Lịch sử thao tác TOÀN BỘ — GET /api/activity?page=N. Gộp mọi scope (đơn/phiếu SX/
thùng) từ audit_events, mới nhất trước, kèm link tới trang chi tiết tương ứng.

Tái dùng nhãn của order_history (đơn) + entity_history (SX/thùng).
"""
from __future__ import annotations

import asyncio
import json
import re

from aiohttp import web

from order_db import _get_connection
from server_app.order_history import _LABELS as _ORDER_LABELS, _actor_display, _detail as _order_detail, _load_names, _norm as _order_norm
from server_app.entity_history import _ACTION_LABELS, _SKIP, _label as _ent_label, _norm as _ent_norm

_PER = 40
_SCOPE_LABEL = {"order": "Đơn", "production": "Phiếu SX", "box": "Thùng"}
_ORDER_ID = re.compile(r"/api/order/(-?\d+)")
# Endpoint chỉ ĐỌC/preview — không phải "thao tác", bỏ khỏi feed (tránh spam khi gõ tạo đơn)
_NOISE = {"/api/order/preview", "/api/order/totals", "/api/order/refresh-view"}
_CREATED_SCOPE = {"order.created": "order", "production.created": "production", "box.created": "box"}


def _href(scope: str, eid) -> str:
    if eid is None:
        return ""
    return {"order": f"#/order/{eid}", "production": f"#/san_xuat/{eid}", "box": f"#/thung/{eid}"}.get(scope, "")


def _body(payload_json) -> dict:
    try:
        b = json.loads(payload_json or "{}").get("body")
        if isinstance(b, str) and b.strip().startswith("{"):
            return json.loads(b)
    except Exception:
        pass
    return {}


def _row_meta(r):
    """1 audit row → (scope, entity_id, label, detail) hoặc None nếu bỏ qua."""
    act = r["action"]
    scope = r["scope"]
    tid = r["thread_id"]
    if act in _ACTION_LABELS:
        return _CREATED_SCOPE[act], tid, _ACTION_LABELS[act], ""
    if act == "order.image_added":
        return "order", tid, "Thêm ảnh", ""
    if act == "order.image_deleted":
        return "order", tid, "Xoá ảnh", ""
    if act != "http.request":
        return None
    source = r["source"] or ""
    if not (source.startswith("POST ") or source.startswith("DELETE ")):
        return None
    # order: cả event có scope='order' (mới) lẫn event CŨ scope=NULL nhưng path là /api/order.
    # Hiện TẤT CẢ mutation (whitelist → nhãn đẹp; còn lại → nhãn generic) để không sót +
    # phân trang không bị hụt.
    if scope == "order" or (scope is None and "/api/order/" in source):
        norm = _order_norm(source.split(" ", 1)[1].split("?")[0])
        if norm in _NOISE:
            return None
        method, key, path = _ent_norm(source)
        label = _ORDER_LABELS.get(norm) or _ent_label(key, method, path)
        eid = tid
        if eid is None:
            m = _ORDER_ID.search(source)
            eid = int(m.group(1)) if m else None
        return "order", eid, label, _order_detail(norm, _body(r["payload_json"]))
    if scope in ("production", "box"):
        method, key, path = _ent_norm(source)
        if key in _SKIP:
            return None
        b = _body(r["payload_json"])
        detail = str(b.get("text") or b.get("note") or "")[:50]
        return scope, tid, _ent_label(key, method, path), detail
    return None


_BASE_WHERE = (
    "WHERE ("
    " action IN ('order.created','production.created','box.created','order.image_added','order.image_deleted')"
    " OR (action='http.request' AND (source LIKE 'POST %' OR source LIKE 'DELETE %'))) "
    "AND (scope IN ('order','production','box') "
    "     OR (scope IS NULL AND (source LIKE 'POST /api/order/%' OR source LIKE 'DELETE /api/order/%')))"
)


def get_activity(before: int | None = None, per: int = _PER):
    """Cursor theo id (before). Quét cửa sổ raw rows, lọc hiển thị được, gom tới `per`.
    Trả (items, next_before, has_more). Lọc-sau-phân-trang không tạo trang rỗng."""
    conn = _get_connection()
    try:
        names = _load_names()
        out: list[dict] = []
        cursor = before
        exhausted = False
        # tối đa vài vòng quét (mỗi vòng 300 raw) để lấp đủ `per` kể cả vùng nhiều preview
        for _ in range(20):
            if len(out) >= per or exhausted:
                break
            q = "SELECT id, ts, actor_id, action, source, scope, thread_id, payload_json, result_json FROM audit_events " + _BASE_WHERE
            args: list = []
            if cursor is not None:
                q += " AND id < ?"
                args.append(cursor)
            q += " ORDER BY id DESC LIMIT 300"
            rows = conn.execute(q, args).fetchall()
            if len(rows) < 300:
                exhausted = True
            for r in rows:
                cursor = r["id"]
                meta = _row_meta(r)
                if not meta:
                    continue
                sc, eid, label, detail = meta
                payload = {}
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                except Exception:
                    payload = {}
                try:
                    status = json.loads(r["result_json"] or "{}").get("status")
                except Exception:
                    status = None
                changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
                out.append({
                    "ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                    "action": label, "detail": detail, "scope": sc, "scope_label": _SCOPE_LABEL.get(sc, sc),
                    "entity_id": eid, "href": _href(sc, eid),
                    "changes": changes,                          # diff từng trường (VAT/SP/…)
                    "method": (r["source"] or "").split(" ", 1)[0],  # POST/DELETE
                    "ok": status is None or (isinstance(status, int) and 200 <= status < 300),
                })
                if len(out) >= per:
                    break
        # Với dòng scope=order: lấy SNEAK PEEK nội dung đơn (1 query gộp) thay cho #id
        order_ids = [row["entity_id"] for row in out if row["scope"] == "order" and row["entity_id"] is not None]
        if order_ids:
            peek: dict = {}
            ph = ",".join("?" * len(order_ids))
            for tr in conn.execute(f"SELECT thread_id, json FROM orders WHERE thread_id IN ({ph})", tuple(order_ids)).fetchall():
                try:
                    j = json.loads(tr["json"] or "{}")
                    txt = " ".join((j.get("text") or j.get("text_raw") or "").split())
                    peek[int(tr["thread_id"])] = txt[:60]
                except Exception:
                    pass
            for row in out:
                if row["scope"] == "order" and row["entity_id"] in peek:
                    row["peek"] = peek[row["entity_id"]]
        return out, cursor, not exhausted
    except Exception:
        return [], None, False
    finally:
        conn.close()


async def activity_handler(request: web.Request):
    try:
        before = request.query.get("before")
        before = int(before) if before else None
    except (ValueError, TypeError):
        before = None
    items, next_before, has_more = await asyncio.to_thread(get_activity, before)
    return web.json_response({"ok": True, "items": items, "next_before": next_before, "has_more": has_more})
