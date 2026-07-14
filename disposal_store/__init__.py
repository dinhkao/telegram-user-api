"""disposal_store — bảng `disposal_slips` (app.db): phiếu XUẤT HỦY hàng hóa.

Hai loại:
  • THEO THÙNG (create_disposal): hủy hàng hư/hết hạn từ 1+ thùng, trừ tồn qua
    `inventory_store.allocate_picks(kind='disposal')` (order_thread_id = id phiếu);
    xoá phiếu (admin) xoá allocations → tồn HOÀN LẠI.
  • BOX-LESS (create_manual_disposal): hàng KHÔNG trong thùng (vd hàng khách trả bị
    hủy) — chỉ GHI NHẬN, KHÔNG trừ tồn, `source_return_id` link phiếu trả; xoá = xoá
    mềm (không có tồn để hoàn). `_row_to_slip` gắn `box_less`.
`items` JSON là snapshot hiển thị. Ai dùng: server_app/disposal_routes,
server_app/return_routes. Connection qua utils.db, 100% local — không đụng KiotViet.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from inventory_store.allocations import allocate_picks
from utils.db import transaction

_VN_TZ = timezone(timedelta(hours=7))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS disposal_slips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    items      TEXT NOT NULL DEFAULT '[]',
    source_return_id INTEGER,
    deleted_at TEXT,
    deleted_by TEXT
)
"""


def _now() -> str:
    return datetime.now(_VN_TZ).isoformat(timespec="seconds")


def ensure_table(conn) -> None:
    conn.execute(_CREATE_SQL)
    # DB cũ tạo trước khi có phiếu hủy box-less (hàng khách trả) — migration idempotent.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(disposal_slips)").fetchall()}
    if "source_return_id" not in cols:
        conn.execute("ALTER TABLE disposal_slips ADD COLUMN source_return_id INTEGER")


def _row_to_slip(row) -> dict:
    slip = dict(row)
    try:
        slip["items"] = json.loads(slip.get("items") or "[]")
    except (TypeError, ValueError):
        slip["items"] = []
    slip["total_quantity"] = round(sum(float(i.get("quantity") or 0) for i in slip["items"]), 3)
    # box_less = phiếu KHÔNG gắn thùng (hàng khách trả) → chỉ ghi nhận, không trừ tồn.
    slip["box_less"] = bool(slip["items"]) and not any(i.get("box_id") for i in slip["items"])
    return slip


def create_disposal(conn, picks, *, reason: str, by: str | None = None) -> tuple[dict | None, str | None]:
    """Tạo phiếu hủy + trừ tồn nguyên tử. picks=[{box_id, quantity?}] (quantity
    thiếu = hủy hết phần còn lại của thùng — allocate_picks kẹp theo remaining,
    bỏ qua thùng vô hiệu/hết hàng). Trả (slip, None) hoặc (None, lý do lỗi)."""
    reason = str(reason or "").strip()
    if not reason:
        return None, "Cần nhập lý do hủy"
    if not picks:
        return None, "Chưa chọn thùng nào"

    class _NoStock(Exception):
        pass

    try:
        with transaction(conn):
            cur = conn.execute(
                "INSERT INTO disposal_slips (created_at, created_by, reason, items) VALUES (?, ?, ?, ?)",
                (_now(), by or "", reason, "[]"),
            )
            slip_id = cur.lastrowid
            done = allocate_picks(conn, picks, slip_id, by=by, kind="disposal")
            if not done:
                raise _NoStock()
            conn.execute(
                "UPDATE disposal_slips SET items = ? WHERE id = ?",
                (json.dumps(done, ensure_ascii=False), slip_id),
            )
    except _NoStock:
        return None, "Thùng đã hết hàng hoặc vô hiệu — không hủy được"
    return get_disposal(conn, slip_id), None


def create_manual_disposal(conn, items, *, reason: str, by: str | None = None,
                           source_return_id=None) -> tuple[dict | None, str | None]:
    """Phiếu hủy BOX-LESS — hàng KHÔNG nằm trong thùng kho (vd hàng khách trả bị hủy).

    Chỉ GHI NHẬN việc hủy: items = [{product_code, quantity, product_unit?}] lưu thẳng,
    KHÔNG tạo allocation, KHÔNG trừ tồn thùng. Xoá phiếu chỉ xoá mềm (không có tồn để
    hoàn). Trả (slip, None) hoặc (None, lý do lỗi)."""
    ensure_table(conn)
    reason = str(reason or "").strip()
    if not reason:
        return None, "Cần nhập lý do hủy"
    clean = []
    for it in items or []:
        code = str(it.get("product_code") or it.get("sp") or "").strip().upper()
        raw = it.get("quantity")
        if raw is None:
            raw = it.get("sl")
        try:
            q = float(raw)
        except (TypeError, ValueError):
            continue
        if not code or q <= 0:
            continue
        clean.append({
            "product_code": code, "quantity": q,
            "product_unit": str(it.get("product_unit") or "").strip(),
            "from_return": source_return_id,
        })
    if not clean:
        return None, "Không có hàng hợp lệ để hủy"
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO disposal_slips (created_at, created_by, reason, items, source_return_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (_now(), by or "", reason, json.dumps(clean, ensure_ascii=False), source_return_id),
        )
        slip_id = cur.lastrowid
    return get_disposal(conn, slip_id), None


def get_disposal(conn, slip_id) -> dict | None:
    row = conn.execute("SELECT * FROM disposal_slips WHERE id = ?", (slip_id,)).fetchone()
    return _row_to_slip(row) if row else None


def list_disposals(conn, *, limit: int = 200) -> list[dict]:
    """Phiếu hủy chưa xoá, mới nhất trước."""
    rows = conn.execute(
        "SELECT * FROM disposal_slips WHERE deleted_at IS NULL ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [_row_to_slip(r) for r in rows]


def backfill_timeline_events(conn) -> int:
    """Bù sự kiện timeline cho phiếu hủy tạo trước khi có audit theo thùng/vị trí.

    Idempotent theo (action, scope, box, disposal_id). Vị trí lấy từ thùng hiện tại;
    đây là best-effort cho dữ liệu cũ, còn mọi phiếu mới được route chụp chính xác.
    """
    ensure_table(conn)
    made = 0
    rows = conn.execute("SELECT * FROM disposal_slips ORDER BY id").fetchall()
    for row in rows:
        slip = _row_to_slip(row)
        for item in slip.get("items") or []:
            try:
                box_id = int(item.get("box_id"))
                taken = float(item.get("quantity") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
            b = conn.execute(
                "SELECT b.id, b.box_code, COALESCE(p.code,b.product_code) product_code, "
                "b.quantity, b.place_id FROM inventory_boxes b "
                "LEFT JOIN products p ON p.id=b.product_id WHERE b.id=?", (box_id,),
            ).fetchone()
            if not b:
                continue
            used = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id=?", (box_id,),
            ).fetchone()[0]
            current = float(b["quantity"] or 0) - float(used or 0)
            events = [("box.disposed", slip.get("created_at"), slip.get("created_by"),
                       current if not slip.get("deleted_at") else max(0.0, current - taken))]
            if slip.get("deleted_at"):
                events.append(("box.disposal_released", slip.get("deleted_at"), slip.get("deleted_by"), current))
            for action, ts, actor, remaining in events:
                payload = json.dumps({
                    "box_id": box_id, "box_code": b["box_code"], "product_code": b["product_code"],
                    "quantity": b["quantity"], "remaining": remaining, "taken": taken,
                    "disposal_id": slip["id"], "disposal_reason": slip.get("reason") or "",
                }, ensure_ascii=False, separators=(",", ":"))
                for scope, entity_id in (("box", box_id), ("place", b["place_id"])):
                    if not entity_id:
                        continue
                    exists = conn.execute(
                        "SELECT 1 FROM audit_events WHERE action=? AND scope=? AND thread_id=? "
                        "AND CAST(json_extract(payload_json,'$.disposal_id') AS INTEGER)=? LIMIT 1",
                        (action, scope, entity_id, slip["id"]),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        "INSERT INTO audit_events (ts,request_id,actor_type,actor_id,action,source,scope,thread_id,payload_json) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (ts or _now(), f"disposal-timeline:{slip['id']}:{box_id}:{action}:{scope}",
                         "web_user", actor or "", action, "disposal.backfill", scope, entity_id, payload),
                    )
                    made += 1
    return made


def delete_disposal(conn, slip_id, *, by: str | None = None) -> tuple[int, str | None]:
    """Xoá phiếu (admin): xoá allocations kind='disposal' → TỒN HOÀN LẠI các thùng,
    phiếu xoá mềm giữ lịch sử. Trả (số dòng allocation đã hoàn, None) hoặc (0, lỗi)."""
    with transaction(conn):
        row = conn.execute("SELECT id, deleted_at FROM disposal_slips WHERE id = ?", (slip_id,)).fetchone()
        if not row:
            return 0, "Không tìm thấy phiếu hủy"
        if row["deleted_at"]:
            return 0, "Phiếu đã xoá rồi"
        cur = conn.execute(
            "DELETE FROM box_allocations WHERE order_thread_id = ? AND kind = 'disposal'",
            (slip_id,),
        )
        conn.execute(
            "UPDATE disposal_slips SET deleted_at = ?, deleted_by = ? WHERE id = ?",
            (_now(), by or "", slip_id),
        )
        return cur.rowcount, None
