from __future__ import annotations

import json

from aiohttp import web

from server_app.orders_db import ensure_orders_fts, ensure_orders_stats_columns, get_orders_conn, search_orders_fts

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
    ts = j.get("task_status", {}) or {}
    try:
        from renderers.order_parts import status_icons
        task_icons = status_icons(ts)   # 5 icon y hệt main message Telegram
    except Exception:
        task_icons = ""
    nop_t = ts.get("nop_tien", {}) or {}
    nop_note = nop_t.get("note") or ""
    # Ảnh gắn với công đoạn: soạn hàng chọn từ pool (note 'imgs:1,2'); nộp tiền chụp
    # mới (note '<code>;img:5'). Tách ra để dashboard ưu tiên thumb soạn→nộp.
    soan_note = (ts.get("soan_hang", {}) or {}).get("note") or ""
    soan_img_ids = [int(x) for x in soan_note[5:].split(",") if x.strip().isdigit()] if soan_note.startswith("imgs:") else []
    nop_img_id = None
    if ";img:" in nop_note:
        nop_note, _tail = nop_note.split(";img:", 1)     # nop_note = code sạch để hiển thị
        if _tail.strip().isdigit():
            nop_img_id = int(_tail.strip())
    # Tên người giao / người nộp (cho nhãn trạng thái workflow)
    try:
        from bot_core.config import USER_NAMES
        giao_by_raw = (ts.get("giao_hang", {}) or {}).get("by")
        giao_by = USER_NAMES.get(str(giao_by_raw), "") if giao_by_raw else ""
        nop_by = USER_NAMES.get(str(nop_t.get("by")), "") if nop_t.get("by") else ""
    except Exception:
        giao_by = nop_by = ""
    inv = j.get("invoice") or []
    invoice_items = [{"sp": it.get("sp", "?"), "sl": it.get("sl", it.get("quantity", it.get("sl1pc", 0)) or 0), "price": int(it.get("price", 0) or 0)} for it in inv]
    return {"key": r["firebase_key"], "thread_id": r["thread_id"], "channel_id": r["channel_id"], "message_id": r["message_id"], "customer": customer, "total": total, "paid": paid, "remaining": max(0, raw_total - paid), "phone": pc.get("sdt", ""), "date": date, "status": j.get("trang_thai", ""), "soan": j.get("soan", False), "giao": j.get("giao", False), "nop": j.get("nop", False), "nhan": j.get("nhan", False), "nhan_tien_note": (ts.get("nhan_tien", {}) or {}).get("note", ""), "done_after_20250124": j.get("done_after_20250124", False), "updated_at": r["updated_at"], "hd_code": hd_code, "creator": creator, "giao_by": giao_by, "nop_by": nop_by, "nop_note": nop_note, "task_icons": task_icons, "text": (j.get("text") or j.get("text_raw") or ""), "created": j.get("created"), "topic_name": j.get("topic_name", ""), "invoice_count": len(inv), "invoice_summary": [{"sp": it["sp"], "sl": it["sl"]} for it in invoice_items[:5]], "invoice_items": invoice_items, "vat": int(j.get("vat", 0) or 0), "pvc": int(j.get("pvc", 0) or 0), "discount": int(j.get("discount", 0) or 0), "no_truoc": pc.get("no_truoc", ""), "kh_debt": (j.get("khDebt") if j.get("khDebt") is not None else j.get("invoice_debt_snapshot")), "tongtienhang": pc.get("tongtienhang", ""), "ngay_giao": j.get("ngay_giao") or "", "giao_done": bool((ts.get("giao_hang") or {}).get("done")), "soan_img_ids": soan_img_ids, "nop_img_id": nop_img_id}


def _attach_thumbs(conn, orders: list[dict]) -> None:
    """Gắn 2 ảnh mới nhất (thumb_image_ids) + ảnh mới nhất (thumb_image_id) + tổng số
    ảnh (image_count) của mỗi đơn — 1 truy vấn gộp cho cả trang. image_count để card
    hiện badge "+N"; thumb_image_ids để card cao hiện tối đa 2 thumbnail.
    Bảng order_images có thể chưa tồn tại (chưa ai thêm ảnh) → bỏ qua an toàn."""
    ids = [o["thread_id"] for o in orders if o.get("thread_id") is not None]
    m: dict = {}
    if ids:
        try:
            ph = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT thread_id, id, kind FROM order_images WHERE thread_id IN ({ph}) ORDER BY thread_id, id DESC",
                ids,
            ).fetchall()
            for row in rows:
                m.setdefault(row["thread_id"], []).append((row["id"], row["kind"]))
        except Exception:
            m = {}
    for o in orders:
        lst = m.get(o.get("thread_id"), [])   # [(id, kind)] mới→cũ
        # Ưu tiên thumb theo LOẠI ảnh: soạn hàng → nhận tiền (nop_tien) → còn lại.
        # Kèm ảnh đã chọn ở task soạn/nộp (note) vào đúng nhóm. Giữ thứ tự mới→cũ.
        soan_note = set(o.get("soan_img_ids") or [])
        nop_note = o.get("nop_img_id")
        soan, nop, rest = [], [], []
        for iid, kind in lst:
            if kind == "soan_hang" or iid in soan_note:
                soan.append(iid)
            elif kind == "nop_tien" or iid == nop_note:
                nop.append(iid)
            else:
                rest.append(iid)
        ordered = soan + nop + rest
        o["thumb_image_id"] = ordered[0] if ordered else None
        o["thumb_image_ids"] = ordered[:2]
        o["image_count"] = len(lst)


def _attach_latest_action(conn, orders: list[dict]) -> None:
    """Gắn thao tác MỚI NHẤT của mỗi đơn — GIÀU như Lịch sử thao tác: nhãn + chi tiết
    ngắn + danh sách thay đổi cũ→mới (changes) + người làm + thời gian. Cho view sort
    'Mới cập nhật'. Lấy từ audit_events (POST có nhãn trong _LABELS, hoặc thêm ảnh);
    1 truy vấn gộp, 8 dòng mới nhất/đơn (window). Tái dùng _norm/_LABELS/_detail/
    _actor_display của order_history (payload_json.changes do audit ghi sẵn). Lỗi→bỏ qua."""
    for o in orders:
        o["last_action"] = o["last_detail"] = o["last_actor"] = o["last_action_ts"] = None
        o["last_changes"] = []
    ids = [o["thread_id"] for o in orders if o.get("thread_id") is not None]
    if not ids:
        return
    try:
        import json
        from server_app.order_history import _norm, _LABELS, _detail, _actor_display, _load_names
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""SELECT thread_id, ts, source, actor_id, action, payload_json FROM (
                    SELECT thread_id, ts, source, actor_id, action, payload_json,
                           ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY id DESC) rn
                    FROM audit_events
                    WHERE thread_id IN ({ph})
                      AND (action = 'order.image_added' OR (action = 'http.request' AND source LIKE 'POST %'))
                ) WHERE rn <= 8 ORDER BY thread_id, rn""",
            ids,
        ).fetchall()
        names = _load_names()
        best: dict = {}
        for r in rows:
            tid = r["thread_id"]
            if tid in best:
                continue
            detail, changes = "", []
            if r["action"] == "order.image_added":
                label = "Thêm ảnh"
            else:
                src = r["source"] or ""
                if not src.startswith("POST "):
                    continue
                norm = _norm(src[5:].split("?")[0])
                label = _LABELS.get(norm)
                if not label:
                    continue
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                    b = payload.get("body")
                    body = json.loads(b) if isinstance(b, str) and b.strip().startswith("{") else {}
                    d = _detail(norm, body)
                    if d and d != norm.rsplit("/", 1)[-1]:  # bỏ detail trùng tên path
                        detail = d
                    ch = payload.get("changes")
                    if isinstance(ch, list):
                        changes = ch
                except Exception:
                    pass
            best[tid] = {"action": label, "detail": detail, "changes": changes,
                         "actor": _actor_display(r["actor_id"], names), "ts": r["ts"]}
    except Exception:
        return
    for o in orders:
        v = best.get(o.get("thread_id"))
        if v:
            o["last_action"] = v["action"]
            o["last_detail"] = v["detail"] or None
            o["last_changes"] = v["changes"]
            o["last_actor"] = v["actor"]
            o["last_action_ts"] = v["ts"]


def build_row_for_thread(thread_id) -> dict | None:
    """Đọc 1 đơn theo thread_id → dựng row danh sách (hoặc None nếu không có/đã xoá).
    Dùng bởi server_app/realtime.py để đẩy dòng đã thay đổi qua WebSocket."""
    conn = get_orders_conn()
    try:
        r = conn.execute(f"SELECT {_ROW_COLUMNS} FROM orders o WHERE o.thread_id = ? AND o.deleted_at IS NULL", (thread_id,)).fetchone()
        if r is None:
            return None
        row = _build_order_row(r)
        _attach_thumbs(conn, [row])
        _attach_latest_action(conn, [row])
        return row
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
    ensure_orders_stats_columns(conn)  # cột generated + index cho stats/filter (SQLite)

    # Engine-specific exprs — cần trước khi dựng WHERE để lọc pending/done.
    # Cả 2 engine dùng cột generated indexed (has_customer, is_done) → đếm bằng
    # index thay vì quét toàn bảng + json_extract mỗi dòng (~66ms → ~1ms).
    from utils.db import IS_POSTGRES
    if IS_POSTGRES:
        has_data = "o.has_customer"
        created_expr = "o.order_created"
        _done = "json_extract(o.json, '$.done_after_20250124')"
        _is_done = f"{_done} = 'true'"
        _is_pending = f"{_done} IS DISTINCT FROM 'true'"
    else:
        has_data = "o.has_customer = 1"
        created_expr = "o.order_created"  # cột generated = json_extract('$.created'), khớp idx_orders_list
        _is_done = "o.is_done = 1"
        _is_pending = "o.is_done = 0"
    has_col = "o.has_customer"  # cột thô để ORDER BY (khớp index) — cả 2 engine

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
    else:
        # Lọc theo bước workflow chưa xong (chưa soạn/giao/nộp/nhận) — dùng cờ gốc
        _stage = {"chua_soan": "soan", "chua_giao": "giao", "chua_nop": "nop", "chua_nhan": "nhan"}.get(filt)
        if _stage:
            e = f"json_extract(o.json, '$.{_stage}')"
            not_done = f"{e} IS DISTINCT FROM 'true'" if IS_POSTGRES else f"{e} IS NOT 1"
            # "Chưa nộp" chỉ tính đơn ĐÃ GIAO rồi (giao xong mới tới lượt nộp tiền).
            extra = ""
            if filt == "chua_nop":
                g = "json_extract(o.json, '$.giao')"
                giao_done = f"{g} IS NOT DISTINCT FROM 'true'" if IS_POSTGRES else f"{g} IS 1"
                extra = f" AND ({giao_done})"
            # Chỉ đơn tạo sau 01/06/2026 — data cũ cờ soạn/giao/nộp/nhận lộn xộn.
            # order_created là ISO ('2026-07-01T…') nên so sánh chuỗi là đúng thứ tự.
            where.append(f"({has_data}) AND ({not_done}){extra} AND (o.order_created >= '2026-06-01')")
    where_clause = " AND ".join(where)
    sort = request.query.get("sort", "created").strip()
    if sort == "date":
        dt_raw = "json_extract(o.json, '$.hoadon.print_content.datetime')"
        dt_expr = f"substr({dt_raw}, 7, 4) || '-' || substr({dt_raw}, 4, 2) || '-' || substr({dt_raw}, 1, 2) || ' ' || substr({dt_raw}, 12, 5)"
        has_dt = f"{dt_raw} IS NOT NULL AND {dt_raw} != ''"
        order_by = f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, CASE WHEN {has_dt} THEN 0 ELSE 1 END ASC, CASE WHEN {has_dt} THEN {dt_expr} ELSE {created_expr} END DESC"
    elif sort == "created":
        # Mặc định: MỚI NHẤT trước, KHÔNG ưu tiên "có khách" — để đơn mới (kể cả
        # chưa gán khách) luôn lên đầu, không bị đẩy xuống đáy. Khớp idx_orders_created_tid
        # (order_created DESC, thread_id DESC) → không TEMP B-TREE (<1ms).
        order_by = f"{created_expr} DESC, o.thread_id DESC"
    elif sort == "updated":
        # 'Mới cập nhật': theo lần sửa gần nhất. Khớp idx_orders_updated_tid → <1ms.
        order_by = "o.updated_at DESC, o.thread_id DESC"
    else:
        order_by = f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, o.updated_at DESC, o.thread_id DESC"
    try:
        total_row = conn.execute(f"SELECT COUNT(*) FROM orders o WHERE {where_clause}", params).fetchone()
        rows = conn.execute(f"SELECT {_ROW_COLUMNS} FROM orders o WHERE {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        orders = [_build_order_row(r) for r in rows]
        _attach_thumbs(conn, orders)  # gắn ảnh đại diện cho từng đơn (1 truy vấn gộp)
        if sort == "updated":  # view 'Mới cập nhật': gắn thao tác mới nhất/đơn
            _attach_latest_action(conn, orders)
        total = int(total_row[0]) if total_row else 0
        stats = {}
        if page == 1:
            # _is_done/_is_pending/has_data đã định nghĩa ở trên (dùng chung với filter).
            stat_row = conn.execute(f"SELECT COUNT(*) as cnt, COUNT(CASE WHEN {_is_done} THEN 1 END) as done, COUNT(CASE WHEN {_is_pending} THEN 1 END) as pending FROM orders o WHERE o.deleted_at IS NULL AND ({has_data})").fetchone()
            stats = {"total_orders": stat_row["cnt"] or 0, "pending": stat_row["pending"] or 0, "done": stat_row["done"] or 0} if stat_row else {"total_orders": 0, "pending": 0, "done": 0}
            # Đếm 4 bước chưa xong (chỉ đơn từ 01/06/2026 — khớp filter). Tập nhỏ nên nhanh.
            def _nd(fld):
                e = f"json_extract(o.json, '$.{fld}')"
                return f"{e} IS DISTINCT FROM 'true'" if IS_POSTGRES else f"{e} IS NOT 1"
            def _dn(fld):  # bước ĐÃ xong
                e = f"json_extract(o.json, '$.{fld}')"
                return f"{e} IS NOT DISTINCT FROM 'true'" if IS_POSTGRES else f"{e} IS 1"
            # chua_nop = chưa nộp NHƯNG đã giao (khớp filter ở trên)
            stg = conn.execute(f"SELECT COUNT(CASE WHEN {_nd('soan')} THEN 1 END) s, COUNT(CASE WHEN {_nd('giao')} THEN 1 END) g, COUNT(CASE WHEN {_nd('nop')} AND {_dn('giao')} THEN 1 END) n, COUNT(CASE WHEN {_nd('nhan')} THEN 1 END) nh FROM orders o WHERE o.deleted_at IS NULL AND ({has_data}) AND o.order_created >= '2026-06-01'").fetchone()
            if stg:
                stats.update({"chua_soan": stg["s"] or 0, "chua_giao": stg["g"] or 0, "chua_nop": stg["n"] or 0, "chua_nhan": stg["nh"] or 0})
        return web.json_response({"orders": orders, "total": total, "page": page, "limit": limit, "total_pages": max(1, (total + limit - 1) // limit), "stats": stats})
    finally:
        conn.close()


async def orders_delivery_handler(request: web.Request):
    """Đơn theo NGÀY GIAO trong 1 tháng (query month=YYYY-MM) — cho lịch giao.
    Trả rows compact (shape _build_order_row, đã gắn thumb) để webapp gom theo ngày."""
    import re
    month = (request.query.get("month") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", month):
        return web.json_response({"ok": False, "error": "month phải dạng YYYY-MM"}, status=400)
    conn = get_orders_conn()
    try:
        rows = conn.execute(
            f"SELECT {_ROW_COLUMNS} FROM orders o "
            "WHERE substr(json_extract(o.json, '$.ngay_giao'), 1, 7) = ? AND o.deleted_at IS NULL "
            "ORDER BY json_extract(o.json, '$.ngay_giao')",
            (month,),
        ).fetchall()
        orders = [_build_order_row(r) for r in rows]
        _attach_thumbs(conn, orders)
        return web.json_response({"ok": True, "month": month, "orders": orders})
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
        # Ánh xạ id nhân viên → tên (task 'by', người tạo HĐ) để hiển thị tên thay vì id
        user_names = {}
        try:
            from bot_core.config import USER_NAMES
            ids = {str(t.get("by")) for t in (j.get("task_status", {}) or {}).values() if t.get("by")}
            ids |= {str(x) for x in (j.get("nguoi_tao_HD") or [])}
            user_names = {i: USER_NAMES[i] for i in ids if i in USER_NAMES}
        except Exception:
            pass
        return web.json_response({"key": row["firebase_key"], "thread_id": row["thread_id"], "channel_id": row["channel_id"], "message_id": row["message_id"], "updated_at": row["updated_at"], "data": j, "chat_messages": [dict(r) for r in chat_rows], "user_names": user_names})
    finally:
        conn.close()
