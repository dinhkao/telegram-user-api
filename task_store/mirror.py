"""MIRROR task của ĐƠN → bảng `tasks` (dual-write, blob vẫn là nguồn sự thật).

Gọi từ order_store.tasks (set/clear_task_status) + order_store.custom_tasks
(thêm/xoá) — best-effort: mirror lỗi KHÔNG được làm hỏng flow đơn (try/except ở
caller). Backfill 1 lần cho đơn có sẵn (order_created >= 2026-06-01, khớp mốc
dữ liệu sạch của dashboard). Nối: task_store.schema/queries, bảng orders.
"""
from __future__ import annotations

import json
import logging
import time

from .schema import conn_tasks

log = logging.getLogger("task_store")

STEP_LABELS = {
    "ban_hd": "Bán HĐ", "soan_hang": "Soạn hàng", "giao_hang": "Giao hàng",
    "nop_tien": "Nộp tiền", "nhan_tien": "Nhận tiền",
}


def order_label_of(data: dict) -> str:
    """Nhãn đơn ngắn cho list việc (khỏi join): khách trên HĐ > tên khách > topic."""
    pc = (data.get("hoadon") or {}).get("print_content") or {}
    return (pc.get("kh") or data.get("customer_name") or data.get("topic_name")
            or (data.get("text") or "")[:40] or "?")


def _iso_epoch(v) -> int | None:
    if not v:
        return None
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _upsert(kind: str, thread_id: int, step_key: str, title: str, *, done: bool,
            done_by: str | None, done_at, order_label: str, created_at: int | None = None) -> None:
    """created_at = NGÀY TẠO ĐƠN (mirror) — sort 'mới tạo' của dashboard việc mới đúng."""
    now = int(time.time())
    conn = conn_tasks()
    try:
        conn.execute(
            "INSERT INTO web_tasks (kind, thread_id, step_key, title, note, order_label, done, done_by, done_at,"
            " created_by, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(kind, thread_id, step_key) WHERE step_key IS NOT NULL DO UPDATE SET"
            " title = excluded.title, order_label = excluded.order_label, done = excluded.done,"
            " done_by = excluded.done_by, done_at = excluded.done_at, updated_at = excluded.updated_at,"
            " created_at = excluded.created_at, deleted_at = NULL",
            (kind, int(thread_id), step_key, title, "", order_label,
             1 if done else 0, done_by, _iso_epoch(done_at) if isinstance(done_at, str) else done_at,
             "", created_at or now, now),
        )
    finally:
        conn.close()


def mirror_order_tasks(thread_id: int, data: dict) -> None:
    """Đồng bộ MỌI task của 1 đơn (5 bước + custom) từ blob → bảng tasks.
    Gọi sau mỗi lần blob đổi task — idempotent (upsert theo mirror key)."""
    label = order_label_of(data)
    created = _iso_epoch(data.get("created"))   # ngày tạo ĐƠN
    ts = data.get("task_status") or {}
    # Nộp tiền xong kiểu KÝ TOA → bước 'nhận tiền' đổi tên 'Gửi toa cho khách'
    _nop = ts.get("nop_tien") or {}
    _gui_toa = bool(_nop.get("done")) and str(_nop.get("note", "")).lower().split(";")[0] in ("co_ky_toa", "khong_ky_toa")
    for key, title in STEP_LABELS.items():
        st = ts.get(key) or {}
        if key == "nhan_tien" and _gui_toa:
            title = "Gửi toa cho khách"
        _upsert("order_step", thread_id, key, title,
                done=bool(st.get("done")), done_by=str(st.get("by") or "") or None,
                done_at=st.get("at"), order_label=label, created_at=created)
    live_ids = set()
    for t in data.get("custom_tasks") or []:
        tid = t.get("id")
        if not tid:
            continue
        live_ids.add(str(tid))
        st = ts.get(tid) or {}
        _upsert("order_custom", thread_id, str(tid), t.get("label") or "?",
                done=bool(st.get("done")), done_by=str(st.get("by") or "") or None,
                done_at=st.get("at"), order_label=label, created_at=created)
    # custom bị xoá khỏi đơn → soft-delete mirror tương ứng
    conn = conn_tasks()
    try:
        rows = conn.execute(
            "SELECT id, step_key FROM web_tasks WHERE kind='order_custom' AND thread_id=? AND deleted_at IS NULL",
            (int(thread_id),)).fetchall()
        for r in rows:
            if r["step_key"] not in live_ids:
                conn.execute("UPDATE web_tasks SET deleted_at=? WHERE id=?", (int(time.time()), r["id"]))
    finally:
        conn.close()


def _tgid_to_username(tgid: str) -> str | None:
    """Telegram id số → username web (fold tên USER_NAMES khớp web_users), như
    cashbox_store.identity. None nếu không map được. Tái dùng build_canon để không
    lặp logic hợp nhất danh tính."""
    try:
        from cashbox_store.identity import build_canon
        try:
            from bot_core.config import USER_NAMES
        except Exception:  # noqa: BLE001
            USER_NAMES = {}
        from user_store import list_users
        rows = list_users()
        users = {u["username"]: (u.get("display_name") or u["username"]) for u in rows}
        canon, _ = build_canon(users, {str(k): v for k, v in USER_NAMES.items()})
        key = canon(str(tgid))
        if key.startswith("user:"):
            return key[5:]
    except Exception:  # noqa: BLE001 — không map được → giữ hành vi cũ (bỏ qua)
        return None
    return None


def auto_assign_nop_tien(thread_id: int, by) -> bool:
    """GIAO HÀNG xong → tự giao việc 'Nộp tiền' của đơn cho người vừa giao,
    hạn CÙNG NGÀY (due_at = ngày VN; giờ 17:00 ghi ở note — cột due_at chỉ chứa
    ngày). Chỉ khi nộp tiền chưa xong + chưa ai được giao (không đè phân công tay).
    `by` = username web, hoặc Telegram id số (map sang username qua identity)."""
    u = str(by or "").strip()
    if u.isdigit():
        mapped = _tgid_to_username(u)
        if mapped:
            u = mapped
    if not u or u.isdigit():
        return False
    from user_store import get_user
    if not get_user(u):
        return False
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    now = int(time.time())
    conn = conn_tasks()
    try:
        cur = conn.execute(
            "UPDATE web_tasks SET assignee = ?, due_at = ?,"
            " note = CASE WHEN note = '' THEN ? ELSE note END, updated_at = ?"
            " WHERE kind = 'order_step' AND thread_id = ? AND step_key = 'nop_tien'"
            " AND deleted_at IS NULL AND done = 0 AND assignee = ''",
            (u, today, "⏰ Hạn 17:00 hôm nay (tự giao sau Giao hàng)", now, int(thread_id)))
        return cur.rowcount > 0
    finally:
        conn.close()


def auto_assign_nhan_tien(thread_id: int) -> bool:
    """NỘP TIỀN xong → tự giao việc 'Nhận tiền' (hoặc 'Gửi toa cho khách' nếu nộp
    kiểu ký toa) của đơn cho DUY. Chỉ khi nhận tiền chưa xong + chưa ai được giao
    (không đè phân công tay)."""
    from user_store import get_user
    if not get_user(_NHAN_TIEN_ASSIGNEE):
        return False
    now = int(time.time())
    conn = conn_tasks()
    try:
        cur = conn.execute(
            "UPDATE web_tasks SET assignee = ?,"
            " note = CASE WHEN note = '' THEN ? ELSE note END, updated_at = ?"
            " WHERE kind = 'order_step' AND thread_id = ? AND step_key = 'nhan_tien'"
            " AND deleted_at IS NULL AND done = 0 AND assignee = ''",
            (_NHAN_TIEN_ASSIGNEE, "(tự giao sau Nộp tiền)", now, int(thread_id)))
        return cur.rowcount > 0
    finally:
        conn.close()


# Người nhận việc 'Nhận tiền / Gửi toa' tự giao sau khi nộp tiền xong (username web)
_NHAN_TIEN_ASSIGNEE = "duy"


def mirror_order_tasks_safe(thread_id: int, data: dict) -> None:
    """Bản bọc try/except — mirror không bao giờ làm hỏng flow đơn."""
    try:
        mirror_order_tasks(int(thread_id), data or {})
    except Exception as e:  # noqa: BLE001
        log.warning("mirror tasks lỗi thread=%s: %s", thread_id, e)


_BACKFILL_DONE = False


def backfill_from_orders() -> int:
    """1 lần mỗi process: mirror mọi đơn từ 2026-06-01 (idempotent — chạy lại vô hại)."""
    global _BACKFILL_DONE
    if _BACKFILL_DONE:
        return 0
    _BACKFILL_DONE = True
    from utils.db import get_connection
    conn = get_connection(readonly=True)
    n = 0
    try:
        rows = conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL"
            " AND order_created >= '2026-06-01' AND thread_id IS NOT NULL").fetchall()
        for r in rows:
            try:
                mirror_order_tasks(r["thread_id"], json.loads(r["json"]))
                n += 1
            except Exception:  # noqa: BLE001 — 1 đơn hỏng không chặn cả đợt
                continue
    finally:
        conn.close()
    log.info("backfill tasks: %d đơn", n)
    return n
