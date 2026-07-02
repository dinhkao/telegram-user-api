from __future__ import annotations

import json

from aiohttp import web

from server_app.orders_db import ensure_orders_fts, get_orders_conn, search_orders_fts

# Cột tối thiểu để dựng 1 dòng danh sách — dùng chung cho list handler và realtime
# (server_app/realtime.build_row_for_thread → đẩy dòng đã đổi qua /ws, khỏi refetch).
_ROW_COLUMNS = "o.firebase_key, o.thread_id, o.channel_id, o.message_id, o.json, o.updated_at"


def _build_order_row(r) -> dict:
    """Dựng 1 dòng đơn cho danh sách webapp từ 1 sqlite Row (các cột _ROW_COLUMNS).
    Nguồn sự thật cho shape của mỗi row — cả /api/orders lẫn realtime đều đi qua đây."""
    try:
        j = json.loads(r["json"])
    except Exception:
        j = {}
    hd, pc = j.get("hoadon", {}) or {}, (j.get("hoadon", {}) or {}).get("print_content", {}) or {}
    customer = pc.get("kh") or j.get("customer_name", "")
    hd_code = hd.get("hd_code") or j.get("kiotvietInvoiceCode", "")
    date = pc.get("datetime", "") or (f"{j.get('created','')[8:10]}/{j.get('created','')[5:7]}/{j.get('created','')[:4]} {j.get('created','')[11:16]}" if j.get("created") else "")
    total = pc.get("tongthanhtoan", "")
    if not total and j.get("invoice"):
        total = f"{sum(int(it.get('price', 0)) * int(it.get('sl', it.get('quantity', 0)) or 0) for it in j.get('invoice', [])):,}".replace(",", ".")
    paid = sum(int(p.get("amount", 0)) for p in (j.get("payments") or []) if str(p.get("amount", 0)).isdigit())
    raw_total = int(str(total).replace(".", "")) if str(total).replace(".", "").isdigit() else 0
    creator = j.get("nguoi_tao_HD")
    creator = ", ".join(str(x) for x in creator) if isinstance(creator, list) else (str(creator) if creator else "")
    return {"key": r["firebase_key"], "thread_id": r["thread_id"], "channel_id": r["channel_id"], "message_id": r["message_id"], "customer": customer, "total": total, "paid": paid, "remaining": max(0, raw_total - paid), "phone": pc.get("sdt", ""), "date": date, "status": j.get("trang_thai", ""), "soan": j.get("soan", False), "giao": j.get("giao", False), "nop": j.get("nop", False), "nhan": j.get("nhan", False), "nhan_tien_note": (j.get("task_status", {}) or {}).get("nhan_tien", {}).get("note", ""), "done_after_20250124": j.get("done_after_20250124", False), "updated_at": r["updated_at"], "hd_code": hd_code, "creator": creator, "text": (j.get("text") or j.get("text_raw") or ""), "topic_name": j.get("topic_name", ""), "invoice_count": len(j.get("invoice", []) or []), "invoice_summary": [{"sp": it.get("sp", "?"), "sl": it.get("sl", it.get("quantity", it.get("sl1pc", 0)) or 0)} for it in (j.get("invoice") or [])[:5]], "no_truoc": pc.get("no_truoc", ""), "tongtienhang": pc.get("tongtienhang", "")}


def build_row_for_thread(thread_id) -> dict | None:
    """Đọc 1 đơn theo thread_id → dựng row danh sách (hoặc None nếu không có/đã xoá).
    Dùng bởi server_app/realtime.py để đẩy dòng đã thay đổi qua WebSocket."""
    conn = get_orders_conn()
    try:
        r = conn.execute(f"SELECT {_ROW_COLUMNS} FROM orders o WHERE o.thread_id = ? AND o.deleted_at IS NULL", (thread_id,)).fetchone()
        return _build_order_row(r) if r is not None else None
    finally:
        conn.close()


async def orders_api_handler(request: web.Request):
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    try:
        limit = max(1, min(200, int(request.query.get("limit", "50"))))
    except ValueError:
        limit = 50
    search = request.query.get("search", "").strip()
    status = request.query.get("status", "").strip()
    filt = request.query.get("filter", "").strip()  # all | pending | done
    offset = (page - 1) * limit
    where, params = ["o.deleted_at IS NULL"], []
    conn = get_orders_conn()

    # Engine-specific exprs — cần trước khi dựng WHERE để lọc pending/done.
    # PG: cột generated indexed (has_customer, order_created) — nhanh 100×.
    # SQLite: json_extract native + expression index đã nhanh.
    from utils.db import IS_POSTGRES
    if IS_POSTGRES:
        has_data = "o.has_customer"
        created_expr = "o.order_created"
    else:
        has_data = "(json_extract(o.json, '$.hoadon.print_content.kh') IS NOT NULL AND json_extract(o.json, '$.hoadon.print_content.kh') != '') OR (json_extract(o.json, '$.customer_name') IS NOT NULL AND json_extract(o.json, '$.customer_name') != '')"
        created_expr = "json_extract(o.json, '$.created')"
    # done_after_20250124 là JSON bool. SQLite json_extract(true)->1; PG (emulation) -> 'true'.
    _done = "json_extract(o.json, '$.done_after_20250124')"
    _is_done = f"{_done} = 'true'" if IS_POSTGRES else f"{_done} = 1"
    _is_pending = f"{_done} IS DISTINCT FROM 'true'" if IS_POSTGRES else f"{_done} IS NOT 1"

    if search:
        ensure_orders_fts(conn)
        fts_ids = search_orders_fts(conn, search)
        if fts_ids is not None:
            where.append(f"o.thread_id IN ({','.join('?' * len(fts_ids))})")
            params.extend(fts_ids)
        else:
            where.append("(o.json LIKE ? OR o.firebase_key LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
    if status:
        where.append("json_extract(o.json, '$.trang_thai') = ?")
        params.append(status)
    # Lọc pending/done server-side — khớp đúng định nghĩa của stats bên dưới
    # (has_data + done_after_20250124) nên số trên chip == số đơn trong danh sách.
    if filt == "pending":
        where.append(f"({has_data}) AND ({_is_pending})")
    elif filt == "done":
        where.append(f"({has_data}) AND ({_is_done})")
    where_clause = " AND ".join(where)
    sort = request.query.get("sort", "created").strip()
    if sort == "date":
        dt_raw = "json_extract(o.json, '$.hoadon.print_content.datetime')"
        dt_expr = f"substr({dt_raw}, 7, 4) || '-' || substr({dt_raw}, 4, 2) || '-' || substr({dt_raw}, 1, 2) || ' ' || substr({dt_raw}, 12, 5)"
        has_dt = f"{dt_raw} IS NOT NULL AND {dt_raw} != ''"
        order_by = f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, CASE WHEN {has_dt} THEN 0 ELSE 1 END ASC, CASE WHEN {has_dt} THEN {dt_expr} ELSE {created_expr} END DESC"
    elif sort == "created":
        order_by = f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, {created_expr} DESC, o.thread_id DESC"
    else:
        order_by = f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, o.updated_at DESC, o.thread_id DESC"
    try:
        total_row = conn.execute(f"SELECT COUNT(*) FROM orders o WHERE {where_clause}", params).fetchone()
        rows = conn.execute(f"SELECT {_ROW_COLUMNS} FROM orders o WHERE {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        orders = [_build_order_row(r) for r in rows]
        total = int(total_row[0]) if total_row else 0
        stats = {}
        if page == 1:
            # _is_done/_is_pending/has_data đã định nghĩa ở trên (dùng chung với filter).
            stat_row = conn.execute(f"SELECT COUNT(*) as cnt, COUNT(CASE WHEN {_is_done} THEN 1 END) as done, COUNT(CASE WHEN {_is_pending} THEN 1 END) as pending FROM orders o WHERE o.deleted_at IS NULL AND ({has_data})").fetchone()
            stats = {"total_orders": stat_row["cnt"] or 0, "pending": stat_row["pending"] or 0, "done": stat_row["done"] or 0} if stat_row else {"total_orders": 0, "pending": 0, "done": 0}
        return web.json_response({"orders": orders, "total": total, "page": page, "limit": limit, "total_pages": max(1, (total + limit - 1) // limit), "stats": stats})
    finally:
        conn.close()


async def order_detail_handler(request: web.Request):
    thread_id = request.match_info.get("thread_id", "").strip()
    if not thread_id:
        return web.json_response({"error": "missing thread_id"}, status=400)
    conn = get_orders_conn()
    try:
        row = conn.execute("SELECT firebase_key, thread_id, channel_id, message_id, json, updated_at FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
        if row is None:
            return web.json_response({"error": "not found"}, status=404)
        try:
            j = json.loads(row["json"])
        except Exception:
            j = {}
        chat_rows = conn.execute("SELECT id, message_id, sender_id, sender_name, text, media_type, created_at FROM order_chat_messages WHERE thread_id = ? ORDER BY created_at ASC", (thread_id,)).fetchall()
        return web.json_response({"key": row["firebase_key"], "thread_id": row["thread_id"], "channel_id": row["channel_id"], "message_id": row["message_id"], "updated_at": row["updated_at"], "data": j, "chat_messages": [dict(r) for r in chat_rows]})
    finally:
        conn.close()
