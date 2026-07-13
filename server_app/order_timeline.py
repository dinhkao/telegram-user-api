"""Timeline biến động của 1 ĐƠN HÀNG — GET /api/order/{thread_id}/timeline.

Đời của đơn trên 1 trục thời gian, kèm RAIL TIỀN CÒN PHẢI THU chạy theo (như
tồn thùng ở box_timeline): tạo đơn → tạo HĐ KiotViet → xuất kho từng thùng →
soạn/giao/nộp/nhận → từng lần thu tiền (−tiền, nợ khách sau thu) → ảnh/bình
luận/sửa đơn. Nguồn: blob đơn (mốc 5 bước + payments — authoritative) + audit
_get_order_history_rows (mọi thao tác khác, đã có parts+link). Nối:
order_store, server_app/order_history, customer_feed._order_total_num.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from aiohttp import web

from order_db import _get_connection

_CAP = 300

# label audit → kind + hướng (in = hàng/tiền VỀ, out = RA). Nhãn 5 bước + thu tiền
# bị LOẠI khỏi phần audit (blob là nguồn chuẩn cho chúng — tránh trùng dòng).
_SKIP_AUDIT_LABELS = {"Công việc", "Đánh dấu soạn", "Đánh dấu bán HĐ", "Đánh dấu giao",
                      "Đánh dấu nộp tiền", "Thu tiền mặt", "Thu chuyển khoản", "Tạo đơn"}
_KIND_BY_LABEL = {
    "Xuất kho cho đơn": ("stock", "out"), "Thu hồi hàng về kho": ("stock", "in"),
    "Chốt xuất kho": ("stock", "neutral"), "Bỏ chốt xuất kho": ("stock", "neutral"),
    "Tạo hoá đơn KiotViet": ("invoice", "neutral"), "Xoá hoá đơn KiotViet": ("invoice", "neutral"),
    "Sửa hoá đơn": ("edit", "neutral"), "Sửa nội dung đơn": ("edit", "neutral"),
    "Gán khách hàng": ("edit", "neutral"), "Đặt ngày giao": ("edit", "neutral"),
    "Thêm ảnh": ("image", "neutral"), "Xóa ảnh": ("image", "neutral"),
    "Bình luận": ("comment", "neutral"), "Bình luận ảnh": ("comment", "neutral"),
    "Thu tiền gộp": ("payment_note", "neutral"), "Xóa thanh toán": ("payment_note", "neutral"),
    "In hoá đơn + phiếu giao": ("print", "neutral"), "Xóa đơn": ("other", "neutral"),
}
_TASK_LABEL = {"ban_hd": "Bán HĐ KiotViet", "soan_hang": "Soạn hàng xong",
               "giao_hang": "Giao hàng xong", "nop_tien": "Nộp tiền xong",
               "nhan_tien": "Nhận tiền xong"}
_NOTE_VI = {"tra_tien_mat": "trả tiền mặt", "co_ky_toa": "có ký toạ", "chuyen_khoan": "chuyển khoản"}


def _epoch(ts) -> float:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _shift_iso(ts, secs: float) -> str:
    """ISO ts + secs giây (neo payment di sản cạnh mốc tạo đơn)."""
    e = _epoch(ts)
    if not e:
        return str(ts or "")
    from datetime import timezone
    return datetime.fromtimestamp(e + secs, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_note(note: str) -> str:
    """note task: 'tra_tien_mat;imgs:875,874' → 'trả tiền mặt' (bỏ đuôi ảnh kỹ thuật —
    token imgs: mang NHIỀU id phân cách phẩy, phải gỡ nguyên cụm trước khi tách)."""
    import re
    s = re.sub(r"\bimgs?:[\d,\s]+", "", str(note or ""))
    outs = []
    for tok in s.replace(",", ";").split(";"):
        tok = tok.strip()
        if not tok:
            continue
        outs.append(_NOTE_VI.get(tok, tok.replace("_", " ")))
    return " · ".join(outs)


def order_timeline(thread_id: int) -> dict:
    from order_store import get_order_by_thread_id
    from server_app.customer_feed import _order_total_num
    from server_app.history_format import Resolver, customer_part, money, part
    from server_app.order_history import _get_order_history_rows, _load_names, _actor_display

    conn = _get_connection()
    try:
        data = get_order_by_thread_id(conn, int(thread_id))
        if not data:
            return {"ok": False, "error": "Không tìm thấy đơn"}
        resolver = Resolver(conn)
        names = _load_names()
        total = _order_total_num(data)
        kh_key = data.get("khach_hang_id")
        kh_name = resolver.customer_name(kh_key) if kh_key is not None else None

        events: list[dict] = []

        def add(ts, kind, dir_, label, parts=None, **extra):
            e = {"ts": _epoch(ts), "at": str(ts or ""), "kind": kind, "dir": dir_,
                 "label": label, "parts": parts or []}
            e.update(extra)
            if e["ts"]:
                events.append(e)

        # 1) mốc từ BLOB — nguồn chuẩn: tạo đơn, 5 bước, từng lần thu tiền
        created = data.get("created")
        creator = _actor_display(str(data.get("creator") or ""), names)
        txt = " ".join(str(data.get("text") or data.get("text_raw") or "").split())
        add(created, "created", "neutral", "Tạo đơn",
            [part(f"“{txt[:60]}”")] + ([part(" · khách "), customer_part(kh_key, resolver)] if kh_key is not None else []),
            actor=creator)
        ts_status = data.get("task_status") or {}
        for key, lbl in _TASK_LABEL.items():
            st = ts_status.get(key) or {}
            if not st.get("done") or not st.get("at"):
                continue
            parts = []
            if key == "ban_hd" and data.get("kiotvietInvoiceCode"):
                parts.append(part(f"HĐ {data.get('kiotvietInvoiceCode')} · {money(total)}"))
            note = _clean_note(st.get("note"))
            if note:
                parts.append(part(f"{' · ' if parts else ''}{note}"))
            if st.get("skip"):
                parts.append(part(" (bỏ qua)"))
            add(st.get("at"), "task", "neutral", lbl, parts,
                actor=_actor_display(str(st.get("by") or ""), names), task=key)
        for p in data.get("payments") or []:
            m = {"cash": "tiền mặt", "transfer": "chuyển khoản"}.get(str(p.get("method") or "").lower(),
                                                                     str(p.get("method") or ""))
            parts = [part(m)] if m else []
            if p.get("new_debt") is not None:
                parts.append(part(f"{' · ' if parts else ''}nợ khách sau thu: {money(p.get('new_debt'))}"))
            # payment đời Node ghi camelCase createdAt; thiếu cả 2 → neo cạnh đơn
            # (không được RỚT — rail tiền phải khớp header)
            pay_ts = p.get("created_at") or p.get("createdAt")
            if not _epoch(pay_ts):
                pay_ts = None
                parts.append(part(f"{' · ' if parts else ''}(không rõ giờ thu)"))
            add(pay_ts or _shift_iso(created, 1.0), "payment", "out", "Thu tiền",
                parts, amount=float(p.get("amount") or 0),
                actor=_actor_display(str(p.get("createdBy") or ""), names))

        # 2) mọi thao tác khác từ audit (đã có nhãn + parts + link + changes)
        pay_events = [e for e in events if e["kind"] == "payment"]

        def _near_payment(ts_h: float, tol: float = 300.0):
            best = None
            for e in pay_events:
                d = abs(e["ts"] - ts_h)
                if d <= tol and (best is None or d < abs(best["ts"] - ts_h)):
                    best = e
            return best

        for h in _get_order_history_rows(conn, int(thread_id), _CAP):
            label = h.get("action") or ""
            if h.get("ok") is False:
                continue
            if label in ("Thu tiền mặt", "Thu chuyển khoản"):
                # blob payment là nguồn chuẩn; request KHÔNG còn payment tương ứng
                # = phiếu thu đã bị XOÁ sau đó → vẫn kể trong câu chuyện (không tính rail)
                if _near_payment(_epoch(h.get("ts"))):
                    continue
                add(h.get("ts"), "payment_note", "neutral", "Thu tiền (phiếu đã xoá sau đó)",
                    h.get("parts") or [], actor=h.get("actor"))
                continue
            if label == "Thu tiền gộp":
                target = _near_payment(_epoch(h.get("ts")))
                if target:   # gắn ngữ cảnh 'gộp + thu tại đơn X' vào chính dòng thu tiền
                    src = [pp for pp in (h.get("parts") or []) if str(pp.get("href", "")).startswith("#/order/")]
                    target["parts"] = target["parts"] + [{"t": " · thu gộp" + (" tại đơn " if src else "")}] + src
                    continue
                # không khớp payment nào (hiếm) → giữ dòng riêng
            if label in _SKIP_AUDIT_LABELS:
                continue
            if label in ("Cập nhật đơn", "Cập nhật đơn (Telegram)") and not (h.get("changes") or h.get("detail")):
                continue   # request lặt vặt / burst auto-parse không nói lên gì
            kind, dir_ = _KIND_BY_LABEL.get(label, ("other", "neutral"))
            add(h.get("ts"), kind, dir_, label, h.get("parts") or [],
                actor=h.get("actor"), changes=h.get("changes") or [],
                image_id=h.get("image_id"))

        # 3) rail tiền: còn phải thu = tổng − Σ đã thu tới thời điểm đó.
        # Đơn di sản không còn dữ liệu hoá đơn (total=0) nhưng CÓ thu tiền → lấy
        # tổng = số đã thu để rail vẫn kể đúng câu chuyện (thay vì 0 suốt đời).
        paid = sum(float(p.get("amount") or 0) for p in data.get("payments") or [])
        rail_total = float(total) if total > 0 else paid
        events.sort(key=lambda e: e["ts"])
        # gộp burst: cùng nhãn + cùng người trong 3 phút, bản sau không thêm gì mới → bỏ
        dedup: list[dict] = []
        for e in events:
            prev = dedup[-1] if dedup else None
            if (prev and e["label"] == prev["label"] and e.get("actor") == prev.get("actor")
                    and e["ts"] - prev["ts"] < 180 and not e.get("changes") and not e.get("parts")):
                continue
            dedup.append(e)
        events = dedup
        paid_running = 0.0
        for e in events:
            if e["kind"] == "payment":
                paid_running += e.get("amount") or 0
            e["remaining"] = max(0.0, rail_total - paid_running)
        events.reverse()   # mới nhất trước (như box timeline)

        return {"ok": True, "items": events[:_CAP], "truncated": len(events) >= _CAP,
                "order": {"thread_id": int(thread_id), "text": txt[:80], "total": total,
                          "paid": paid, "remaining": max(0.0, rail_total - paid),
                          "customer_key": kh_key, "customer_name": kh_name,
                          "kv_code": data.get("kiotvietInvoiceCode") or "",
                          "created": str(created or ""), "ngay_giao": data.get("ngay_giao") or ""}}
    finally:
        conn.close()


async def order_timeline_handler(request: web.Request):
    tid = request.match_info.get("thread_id", "").strip()
    if not tid.lstrip("-").isdigit():
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    data = await asyncio.to_thread(order_timeline, int(tid))
    return web.json_response(data, status=200 if data.get("ok") else 404)
