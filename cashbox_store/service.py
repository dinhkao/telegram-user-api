"""Ráp trạng thái hệ KÉT TIỀN từ blob đơn + transfers (IO + cache RAM).

Đọc orders (từ SINCE) + cashbox_transfers + web_users + USER_NAMES, chạy
cashbox_store.domain cho từng đơn, gộp thành: số dư từng két, danh sách đơn
đang nằm trong két (holdings), timeline biến động. Cache theo stamp
(MAX(orders.updated_at) + đếm/max transfers) — mutation nào cũng đổi stamp nên
tự tươi (POST transfer vẫn gọi invalidate_cache cho chắc). Kết nối:
utils/db.py, server_app/customer_feed (_order_total_num), bot_core.config
(USER_NAMES), user_store; API: server_app/cashbox_routes.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from utils.db import get_connection

from .domain import EXTERNAL, SINCE, aggregate_balances, derive_order_movements, is_overdue, _ts
from .identity import BOX_NAMES, box_display, build_canon
from .queries import list_transfers
from .schema import ensure_table

_VN = timezone(timedelta(hours=7))

_REASON_VI = {
    "giao_hang": "Thu hộ khi giao",
    "nop_tien:tra_tien_mat": "Nộp tiền mặt",
    "nop_tien:co_ky_toa": "Báo nợ (có ký toa)",
    "nop_tien:khong_ky_toa": "Báo nợ (không ký toa)",
    "nop_tien:chieu_lay_tien": "Báo nợ (chiều lấy tiền)",
    "nop_tien:skip": "Nộp — bỏ qua bước",
    "nop_tien:khong_ro": "Nộp không rõ kết quả",
    "payment": "Thu tiền (phiếu thu)",
    "payment_ck": "Thu chuyển khoản",
    "transfer": "Chuyển tiền tay",
    "purchase_pay": "Trả tiền nhập hàng",
}

_cache: dict = {"stamp": None, "state": None}


def invalidate_cache() -> None:
    _cache["stamp"] = None
    _cache["state"] = None


def _since_utc() -> str:
    """Mốc SQL = 00:00 VN của ngày SINCE, đổi sang ISO UTC — order_created là
    chuỗi ISO UTC nên so sánh thẳng ngày VN sẽ lệch 7 tiếng (đơn 0h–7h sáng)."""
    try:
        d = datetime.strptime(SINCE, "%Y-%m-%d").replace(tzinfo=_VN)
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:   # env CASHBOX_SINCE sai dạng → dùng thô
        return SINCE


def _since_epoch() -> float:
    """Epoch của 00:00 VN ngày SINCE — lọc transfer/payment nhập hàng."""
    try:
        return datetime.strptime(SINCE, "%Y-%m-%d").replace(tzinfo=_VN).timestamp()
    except ValueError:
        return 0.0


def _stamp(conn, now: float) -> tuple:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM orders"
        " WHERE deleted_at IS NULL AND order_created >= ?", (_since_utc(),)).fetchone()
    ensure_table(conn)
    t = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(deleted_at), '')"
        " FROM cashbox_transfers").fetchone()
    try:   # user tạo/khoá lúc chạy phải làm mới canon + danh sách két
        u = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(rowid), 0), COALESCE(SUM(disabled), 0)"
            " FROM web_users").fetchone()
        users_sig = (u[0], u[1], u[2])
    except Exception:  # noqa: BLE001 — thiếu bảng (DB test) vẫn chạy
        users_sig = ()
    try:   # payments trả NCC (thêm/gỡ/xoá phiếu) phải làm mới derive
        p = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(payments)), 0),"
            " SUM(CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END)"
            " FROM purchase_slips WHERE payments IS NOT NULL AND payments != '[]'").fetchone()
        pur_sig = (p[0], p[1], p[2])
    except Exception:  # noqa: BLE001
        pur_sig = ()
    # bucket thời gian VN: cờ quá-hạn chỉ lật ở mốc 17:00/nửa đêm, in/out_today
    # đổi ở nửa đêm → đưa (ngày, đã-qua-17h) vào stamp là ĐỦ chính xác, tối đa
    # thêm 2 lần rebuild mỗi ngày.
    d = datetime.fromtimestamp(now, _VN)
    return (row[0], row[1], t[0], t[1], t[2], users_sig, pur_sig,
            d.strftime("%Y-%m-%d"), d.hour >= 17)


def _extra_tg_map() -> dict[str, str]:
    """Env CASHBOX_TG_MAP='tgid=username,...' — ép tay tg-id → web user."""
    out: dict[str, str] = {}
    for pair in os.getenv("CASHBOX_TG_MAP", "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip().lower()
    return out


def _order_label(data: dict) -> str:
    return str(data.get("khach_hang") or data.get("customer_name")
               or data.get("name") or f"Đơn {data.get('thread_id')}").strip()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if ts else ""


def _vn_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, _VN).strftime("%Y-%m-%d") if ts else ""


def _build_state(conn, now: float) -> dict:
    from server_app.customer_feed import _order_total_num  # tránh vòng import lúc boot

    try:
        from bot_core.config import USER_NAMES
    except Exception:  # noqa: BLE001 — thiếu env bot vẫn chạy được phần web
        USER_NAMES = {}
    try:
        from user_store import list_users
        rows = list_users()
    except Exception:  # noqa: BLE001
        rows = []
    # Canon dùng MỌI user (kể cả disabled) — khoá/đổi tên user không được tách két
    # lịch sử của người đó; chỉ SEED két trống cho user đang hoạt động.
    users = {u["username"]: (u.get("display_name") or u["username"]) for u in rows}
    active = [u["username"] for u in rows if not u.get("disabled")]
    canon, names = build_canon(users, {str(k): v for k, v in USER_NAMES.items()}, _extra_tg_map())

    moves: list[dict] = []
    holdings: list[dict] = []
    order_names: dict[int, str] = {}
    for r in conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL"
            " AND order_created >= ? AND json IS NOT NULL", (_since_utc(),)):
        try:
            data = json.loads(r["json"])
        except (json.JSONDecodeError, TypeError):
            continue
        total = _order_total_num(data)
        if total <= 0 and not data.get("payments"):
            continue
        res = derive_order_movements(data, total, canon)
        if r["thread_id"] is not None and (res["moves"] or res["loc"] != EXTERNAL):
            order_names[r["thread_id"]] = _order_label(data)
        moves.extend(res["moves"])
        if res["loc"] != EXTERNAL and res["remaining"] > 0:
            holdings.append({
                "box": res["loc"], "thread_id": r["thread_id"],
                "name": _order_label(data), "amount": res["remaining"],
                "since": res["hold_since"], "since_at": _iso(res["hold_since"]),
                "note": res["hold_note"],
                "overdue": res["loc"].startswith(("user:", "tg:")) and not res["hold_note"]
                and is_overdue(res["hold_since"], now),
            })

    for t in list_transfers(conn):
        moves.append({"ts": _ts(t["created_at"]), "src": t["from_box"], "dst": t["to_box"],
                      "amount": t["amount"], "reason": "transfer", "actor": t["created_by"],
                      "thread_id": None, "transfer_id": t["id"], "note": t["note"]})

    # Trả tiền NCC từ két (phiếu nhập hàng) — tiền RA khỏi hệ két
    try:
        from purchase_store import payments_for_cashbox
        since_ep = _since_epoch()
        for pu in payments_for_cashbox(conn):
            for p in pu["payments"]:
                try:
                    a = int(round(float(p.get("amount") or 0)))
                except (TypeError, ValueError):
                    continue
                ts = _ts(p.get("at"))
                if a <= 0 or ts < since_ep:
                    continue
                moves.append({"ts": ts, "src": str(p.get("box") or "unknown"), "dst": EXTERNAL,
                              "amount": a, "reason": "purchase_pay", "actor": p.get("by"),
                              "thread_id": None, "purchase_id": pu["purchase_id"],
                              "other_label": f"NCC {pu['supplier_name']}".strip()})
    except Exception:  # noqa: BLE001 — bảng nhập hàng chưa có (DB test) vẫn chạy
        pass

    for m in moves:   # tên người thao tác — canon 1 lần lúc build
        a = m.get("actor")
        m["actor_name"] = box_display(canon(a), names) if a not in (None, "") else ""
    moves.sort(key=lambda m: m["ts"])
    balances = aggregate_balances(moves)
    balances.pop(EXTERNAL, None)

    today = _vn_day(now)
    boxes: dict[str, dict] = {}

    def _box(key: str) -> dict:
        if key not in boxes:
            kind = "special" if key in BOX_NAMES else ("user" if key.startswith("user:") else "tg")
            boxes[key] = {"key": key, "name": box_display(key, names), "kind": kind,
                          "balance": 0, "holding_count": 0, "holding_total": 0,
                          "overdue_count": 0, "in_today": 0, "out_today": 0}
        return boxes[key]

    for key in BOX_NAMES:
        _box(key)
    for u in active:
        _box(f"user:{u}")
    for key, bal in balances.items():
        _box(key)["balance"] = bal
    for h in holdings:
        b = _box(h["box"])
        b["holding_count"] += 1
        b["holding_total"] += h["amount"]
        if h["overdue"]:
            b["overdue_count"] += 1
    for m in moves:
        if _vn_day(m["ts"]) != today:
            continue
        if m["dst"] in boxes:
            boxes[m["dst"]]["in_today"] += m["amount"]
        if m["src"] in boxes:
            boxes[m["src"]]["out_today"] += m["amount"]

    return {"moves": moves, "holdings": holdings, "boxes": boxes,
            "order_names": order_names, "names": names}


def _state(now: float) -> dict:
    conn = get_connection()
    try:
        stamp = _stamp(conn, now)
        if _cache["stamp"] == stamp and _cache["state"] is not None:
            return _cache["state"]
        state = _build_state(conn, now)
        _cache["stamp"] = stamp
        _cache["state"] = state
        return state
    finally:
        conn.close()


def _sorted_boxes(boxes: dict[str, dict]) -> list[dict]:
    special_order = {"office": 0, "bank": 1, "debt": 2, "unknown": 3}
    return sorted(boxes.values(),
                  key=lambda b: (0, special_order.get(b["key"], 9), 0, "") if b["kind"] == "special"
                  else (1, 0, -(b["balance"] + b["holding_total"]), b["name"]))


def cashbox_summary(now: float, viewer: str | None = None) -> dict:
    """Tổng quan mọi két. viewer=username (non-office) → chỉ két của họ, KHÔNG
    kèm tổng nợ toàn công ty."""
    st = _state(now)
    boxes = _sorted_boxes(st["boxes"])
    if viewer:
        key = f"user:{viewer.lower()}"
        return {"ok": True, "since": SINCE, "boxes": [b for b in boxes if b["key"] == key]}
    return {"ok": True, "since": SINCE, "boxes": boxes,
            "total_unpaid": sum(h["amount"] for h in st["holdings"] if h["box"] == "debt")}


def box_exists(key: str, now: float) -> bool:
    """Két có thật trong trạng thái hiện tại (đặc biệt / user active / có biến động)?"""
    return key in _state(now)["boxes"]


def cashbox_balance(key: str, now: float) -> int:
    """Số dư hiện tại của 1 két (cho validate chuyển tiền)."""
    st = _state(now)
    box = st["boxes"].get(key)
    return int(box["balance"]) if box else 0


def cashbox_timeline(key: str, now: float, limit: int = 300, before: float | None = None) -> dict:
    """Timeline 1 két: holdings hiện tại + biến động (mới nhất trước, kèm số dư
    sau từng dòng). before = ts phân trang (lấy các dòng cũ hơn)."""
    st = _state(now)
    box = st["boxes"].get(key)
    if not box:
        return {"ok": False, "error": "Không tìm thấy két"}
    items: list[dict] = []
    bal = 0
    for m in st["moves"]:
        if m["src"] != key and m["dst"] != key:
            continue
        incoming = m["dst"] == key
        bal += m["amount"] if incoming else -m["amount"]
        other = m["src"] if incoming else m["dst"]
        tid = m.get("thread_id")
        items.append({
            "ts": m["ts"], "at": _iso(m["ts"]), "dir": "in" if incoming else "out",
            "amount": m["amount"], "after": bal,
            "other_key": other,
            "other_name": m.get("other_label")
            or ("Khách" if other == EXTERNAL else box_display(other, st["names"])),
            "reason": m["reason"], "label": _REASON_VI.get(m["reason"], m["reason"]),
            "thread_id": tid, "order_name": st["order_names"].get(tid, "") if tid else "",
            "transfer_id": m.get("transfer_id"), "purchase_id": m.get("purchase_id"),
            "note": m.get("note", ""),
            "actor": m.get("actor_name", ""),
        })
    if before:
        items = [i for i in items if i["ts"] < before]
    truncated = len(items) > limit
    items = items[-limit:]
    items.reverse()
    holdings = sorted([h for h in st["holdings"] if h["box"] == key], key=lambda h: h["since"])
    return {"ok": True, "box": box, "items": items, "truncated": truncated,
            "holdings": holdings}
