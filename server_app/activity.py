"""Lịch sử thao tác TOÀN BỘ — GET /api/activity?page=N. Gộp MỌI scope (đơn/phiếu
SX/thùng/khách/kho/trả hàng/nhập hàng/quỹ/việc/SP/cài đặt…) từ audit_events, mới
nhất trước, kèm link + parts chi tiết tới trang thực thể được nhắc.

Nhãn/chi tiết: server_app/activity_format (event_format + order/entity_history).
Sneak-peek nội dung thực thể (text đơn, tên khách, SP thùng…) tra gộp 1 query/scope.
"""
from __future__ import annotations

import asyncio
import json

from aiohttp import web

from order_db import _get_connection
from server_app.activity_format import epoch as _epoch, row_meta
from server_app.history_format import Resolver
from server_app.order_history import _actor_display, _load_names

_PER = 40

# Chỉ quét row có thể hiển thị: mọi domain event (≠ http.request) + request GHI.
_BASE_WHERE = (
    "(action != 'http.request' OR source LIKE 'POST %' OR source LIKE 'DELETE %' "
    "OR source LIKE 'PUT %' OR source LIKE 'PATCH %')"
)

# peek theo scope: 1 query gộp mỗi scope cho các entity_id trên trang
_PEEK_SQL = {
    "order": "SELECT thread_id AS id, COALESCE(json_extract(json,'$.text'), json_extract(json,'$.text_raw')) AS v "
             "FROM orders WHERE thread_id IN ({ph})",
    "customer": "SELECT firebase_key AS id, COALESCE(json_extract(json,'$.name'), json_extract(json,'$.ten_khach_hang')) AS v "
                "FROM customers WHERE firebase_key IN ({ph})",
    "box": "SELECT id, product_code || ' · thùng ' || box_code AS v FROM inventory_boxes WHERE id IN ({ph})",
    "place": "SELECT id, name AS v FROM inventory_places WHERE id IN ({ph})",
    "task": "SELECT id, title AS v FROM web_tasks WHERE id IN ({ph})",
    "supplier": "SELECT id, name AS v FROM suppliers WHERE id IN ({ph})",
    "production": "SELECT thread_id AS id, COALESCE(sp_name, date) AS v FROM production_slips WHERE thread_id IN ({ph})",
    "disposal": "SELECT id, reason AS v FROM disposal_slips WHERE id IN ({ph})",
    "return": "SELECT id, customer_key AS v FROM return_slips WHERE id IN ({ph})",
}


def _attach_peeks(conn, out: list[dict]) -> None:
    """Điền row['peek'] = mô tả ngắn thực thể (batched 1 query/scope)."""
    by_scope: dict[str, set] = {}
    for row in out:
        if row.get("entity_id") is not None and row["scope"] in _PEEK_SQL:
            by_scope.setdefault(row["scope"], set()).add(row["entity_id"])
    found: dict[tuple, str] = {}
    for sc, ids in by_scope.items():
        ids = list(ids)
        try:
            sql = _PEEK_SQL[sc].format(ph=",".join("?" * len(ids)))
            for r in conn.execute(sql, tuple(str(i) if sc == "customer" else i for i in ids)).fetchall():
                v = " ".join(str(r["v"] or "").split())[:60]
                if v:
                    found[(sc, str(r["id"]))] = v
        except Exception:
            continue
    # return: peek đang là customer_key → tra tiếp ra tên khách
    ret_keys = {v for (sc, _), v in found.items() if sc == "return"}
    if ret_keys:
        try:
            ph = ",".join("?" * len(ret_keys))
            kh = {str(r["id"]): " ".join(str(r["v"] or "").split())[:60] for r in conn.execute(
                _PEEK_SQL["customer"].format(ph=ph), tuple(ret_keys)).fetchall()}
            for k, v in list(found.items()):
                if k[0] == "return" and v in kh:
                    found[k] = kh[v]
        except Exception:
            pass
    for row in out:
        key = (row["scope"], str(row.get("entity_id")))
        if key in found:
            row["peek"] = found[key]


def get_activity(before: int | None = None, per: int = _PER):
    """Cursor theo id (before). Quét cửa sổ raw rows, lọc hiển thị được, gom tới `per`.
    Trả (items, next_before, has_more). Lọc-sau-phân-trang không tạo trang rỗng."""
    conn = _get_connection()
    try:
        names = _load_names()
        resolver = Resolver(conn)
        out: list[dict] = []
        cursor = before
        exhausted = False
        last_rk = None   # gộp autosave (báo cáo thợ / đếm kiểm kho) liên tiếp
        broke_mid_batch = False   # trang đầy giữa batch cuối → vẫn còn dòng chưa xử lý
        # (thời điểm, entity) các event — để bỏ dòng request trùng event. Cộng dồn
        # QUA các batch: event với request cùng thao tác có thể rơi 2 batch kề nhau.
        event_times: dict[str, list[tuple[float, object]]] = {}
        # tối đa vài vòng quét (mỗi vòng 300 raw) để lấp đủ `per` kể cả vùng nhiều noise
        for _ in range(20):
            if len(out) >= per or exhausted:
                break
            q = ("SELECT id, ts, actor_id, action, source, scope, thread_id, payload_json, result_json "
                 "FROM audit_events WHERE " + _BASE_WHERE)
            args: list = []
            if cursor is not None:
                q += " AND id < ?"
                args.append(cursor)
            q += " ORDER BY id DESC LIMIT 300"
            rows = conn.execute(q, args).fetchall()
            if len(rows) < 300:
                exhausted = True
            for r in rows:
                if (r["action"] or "") != "http.request":
                    event_times.setdefault(r["action"], []).append((_epoch(r["ts"]), r["thread_id"]))
            if rows:
                # nhìn TRƯỚC 100 event kế (id nhỏ hơn) — cặp request↔event có thể
                # rơi 2 bên mép batch (event ghi trước request vài ms)
                try:
                    for r2 in conn.execute(
                        "SELECT action, ts, thread_id FROM audit_events WHERE id < ? AND action != 'http.request' "
                        "ORDER BY id DESC LIMIT 100", (rows[-1]["id"],),
                    ).fetchall():
                        event_times.setdefault(r2["action"], []).append((_epoch(r2["ts"]), r2["thread_id"]))
                except Exception:
                    pass
            for ri, r in enumerate(rows):
                cursor = r["id"]
                meta = row_meta(r, resolver, event_times)
                if not meta:
                    continue
                rk = meta.pop("_rk", None)
                if rk and rk == last_rk:
                    continue   # autosave báo cáo dồn dập → giữ 1 dòng
                last_rk = rk
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                    payload = payload if isinstance(payload, dict) else {}
                except Exception:
                    payload = {}
                try:
                    status = json.loads(r["result_json"] or "{}").get("status")
                except Exception:
                    status = None
                changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
                out.append({
                    "ts": r["ts"], "actor": _actor_display(r["actor_id"], names),
                    "action": meta["label"], "detail": meta["detail"], "parts": meta.get("parts") or [],
                    "scope": meta["scope"], "scope_label": meta["scope_label"],
                    "entity_id": meta["eid"], "href": meta.get("href") or "",
                    "changes": changes,                          # diff từng trường (VAT/SP/…)
                    "method": (r["source"] or "").split(" ", 1)[0] if r["action"] == "http.request" else "",
                    "ok": status is None or (isinstance(status, int) and 200 <= status < 300),
                })
                if len(out) >= per:
                    broke_mid_batch = ri < len(rows) - 1
                    break
        _attach_peeks(conn, out)
        return out, cursor, (not exhausted) or broke_mid_batch
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
