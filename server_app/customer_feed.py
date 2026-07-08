"""Feed ĐƠN + THANH TOÁN của 1 khách, gộp 1 dòng thời gian (trang chi tiết khách).

GET /api/customers/{key}/feed?page= → items xen kẽ theo thời gian giảm dần:
  {kind:'order', ts, order:<row như dashboard>} |
  {kind:'payment', ts, thread_id, amount, method, code, by, at}
Đơn của 1 khách ít (vài chục~trăm) nên dựng index gộp trong RAM rồi phân trang;
row đơn dựng bằng _build_order_row + thumbs — y hệt dashboard để client tái dùng
card. Nối: server_app.orders_api, server_app.orders_db. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web

_PAGE = 20


def _ts_key(v) -> float:
    """Chuỗi thời gian bất kỳ (ISO / epoch s hoặc ms / rỗng) → epoch float để sort."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e12 else x
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        x = float(s)
        return x / 1000.0 if x > 1e12 else x
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _build_feed(conn, key: str, page: int):
    from server_app.orders_api import _ROW_COLUMNS, _build_order_row, _attach_thumbs
    # 1) index gộp: mọi đơn (ts=created) + mọi payment trong blob đơn (ts=created_at)
    idx: list[tuple[float, str, object]] = []
    # CAST AS TEXT: khach_hang_id trong blob khi là số (8) khi là chữ ('8') — so
    # thẳng = ? bỏ sót các đơn lưu dạng số (vd Loan Phú có 8 đơn kiểu integer).
    for r in conn.execute(
        "SELECT o.thread_id, o.json FROM orders o "
        "WHERE CAST(json_extract(o.json, '$.khach_hang_id') AS TEXT) = ? AND o.deleted_at IS NULL",
        (key,),
    ).fetchall():
        tid = r["thread_id"]
        if tid is None:
            continue   # row hỏng/di sản — không dựng được card lẫn link
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        idx.append((_ts_key(data.get("created")) or float(tid), "order", tid))
        for p in data.get("payments") or []:
            idx.append((_ts_key(p.get("created_at")), "payment", {
                "thread_id": tid,
                "amount": p.get("amount") or 0,
                "method": p.get("method") or "",
                "code": p.get("code") or "",
                "by": p.get("createdBy") or p.get("by") or "",
                "at": p.get("created_at"),
            }))
    idx.sort(key=lambda t: t[0], reverse=True)
    total = len(idx)
    chunk = idx[(page - 1) * _PAGE: (page - 1) * _PAGE + _PAGE]

    # 2) dựng row dashboard cho các đơn trong trang này
    order_ids = [t[2] for t in chunk if t[1] == "order"]
    rows_by_id = {}
    if order_ids:
        qs = ",".join("?" * len(order_ids))
        rows = conn.execute(
            f"SELECT {_ROW_COLUMNS} FROM orders o WHERE o.thread_id IN ({qs})", order_ids
        ).fetchall()
        built = [_build_order_row(r) for r in rows]
        _attach_thumbs(conn, built)
        rows_by_id = {o["thread_id"]: o for o in built}

    items = []
    for ts, kind, payload in chunk:
        if kind == "order":
            row = rows_by_id.get(payload)
            if row:
                items.append({"kind": "order", "ts": ts, "order": row})
        else:
            items.append({"kind": "payment", "ts": ts, **payload})
    return items, total


async def customer_feed_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1

    def _run():
        from server_app.orders_db import get_orders_conn
        conn = get_orders_conn()
        try:
            return _build_feed(conn, key, page)
        finally:
            conn.close()

    items, total = await asyncio.to_thread(_run)
    total_pages = max(1, -(-total // _PAGE))
    return web.json_response({"ok": True, "items": items, "page": page,
                              "total_pages": total_pages, "total": total})
