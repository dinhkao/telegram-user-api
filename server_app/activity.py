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
    if act != "http.request":
        return None
    source = r["source"] or ""
    if not (source.startswith("POST ") or source.startswith("DELETE ")):
        return None
    # order: cả event có scope='order' (mới) lẫn event CŨ scope=NULL nhưng path là /api/order
    if scope == "order" or (scope is None and "/api/order/" in source):
        norm = _order_norm(source.split(" ", 1)[1].split("?")[0])
        label = _ORDER_LABELS.get(norm)
        if not label:
            return None
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


def get_activity(page: int = 1, per: int = _PER):
    off = (max(1, page) - 1) * per
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT ts, actor_id, action, source, scope, thread_id, payload_json, result_json "
            "FROM audit_events WHERE ("
            " action IN ('order.created','production.created','box.created','order.image_added')"
            " OR (action='http.request' AND (source LIKE 'POST %' OR source LIKE 'DELETE %'))) "
            "AND (scope IN ('order','production','box') "
            "     OR (scope IS NULL AND (source LIKE 'POST /api/order/%' OR source LIKE 'DELETE /api/order/%'))) "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            (per + 1, off),
        ).fetchall()
        names = _load_names()
        has_more = len(rows) > per
        out = []
        for r in rows[:per]:
            meta = _row_meta(r)
            if not meta:
                continue
            sc, eid, label, detail = meta
            try:
                status = json.loads(r["result_json"] or "{}").get("status")
            except Exception:
                status = None
            out.append({
                "ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                "action": label, "detail": detail, "scope": sc, "scope_label": _SCOPE_LABEL.get(sc, sc),
                "entity_id": eid, "href": _href(sc, eid),
                "ok": status is None or (isinstance(status, int) and 200 <= status < 300),
            })
        return out, has_more
    except Exception:
        return [], False
    finally:
        conn.close()


async def activity_handler(request: web.Request):
    try:
        page = max(1, int(request.query.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    items, has_more = await asyncio.to_thread(get_activity, page)
    return web.json_response({"ok": True, "items": items, "page": page, "has_more": has_more})
