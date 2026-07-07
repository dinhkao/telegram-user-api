"""box_allocations: 1 dòng = 1 phần thùng xuất cho 1 đơn (thùng KHÔNG tách).

remaining của thùng = quantity − tổng allocation. Xuất 1 phần → ghi 1 dòng, thùng
gốc giữ nguyên số cây gốc, còn lại giảm. Thu hồi = xoá dòng. Nối: utils.db.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from utils.db import transaction

_VN_TZ = timezone(timedelta(hours=7))


def _now() -> str:
    return datetime.now(_VN_TZ).isoformat(timespec="seconds")


def create_allocations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS box_allocations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            box_id          INTEGER NOT NULL,
            order_thread_id INTEGER NOT NULL,
            quantity        REAL NOT NULL,
            allocated_at    TEXT,
            allocated_by    TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alloc_box ON box_allocations(box_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alloc_order ON box_allocations(order_thread_id)")
    # kind: 'order' (xuất cho đơn) | 'production' (tiêu hao nguyên liệu khi sản xuất)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(box_allocations)").fetchall()}
    if "kind" not in cols:
        conn.execute("ALTER TABLE box_allocations ADD COLUMN kind TEXT DEFAULT 'order'")
    conn.commit()


def migrate_legacy_allocations(conn):
    """Chuyển thùng xuất kiểu cũ (status allocated/shipped + order_thread_id) sang
    box_allocations — chỉ nếu thùng đó chưa có dòng allocation nào (chạy 1 lần)."""
    try:
        rows = conn.execute(
            "SELECT id, order_thread_id, quantity FROM inventory_boxes "
            "WHERE status IN ('allocated','shipped') AND order_thread_id IS NOT NULL"
        ).fetchall()
    except Exception:
        return
    now = _now()
    for r in rows:
        exists = conn.execute("SELECT 1 FROM box_allocations WHERE box_id = ?", (r[0],)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, allocated_by) "
                "VALUES (?,?,?,?,?)",
                (r[0], r[1], r[2], now, "migrate"),
            )
    conn.commit()


def allocate_picks(conn, picks, order_thread_id, *, by=None, kind="order") -> list[dict]:
    """Xuất kho cho đơn — lấy 1 phần thùng, KHÔNG tách. picks=[{box_id, quantity?}].

    quantity thiếu = lấy hết phần còn lại của thùng. Kẹp theo remaining. Bỏ qua thùng
    vô hiệu / hết còn lại. Nguyên tử. Trả list dòng allocation vừa tạo.
    kind='production' = tiêu hao nguyên liệu khi sản xuất (order_thread_id = phiếu SX).
    """
    if not picks:
        return []
    now = _now()
    out: list[dict] = []
    with transaction(conn):
        for p in picks:
            try:
                bid = int(p.get("box_id"))
            except (TypeError, ValueError, AttributeError):
                continue
            row = conn.execute("SELECT * FROM inventory_boxes WHERE id = ?", (bid,)).fetchone()
            if not row:
                continue
            box = dict(row)
            if box.get("disabled"):
                continue
            allocated = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?", (bid,)
            ).fetchone()[0]
            remaining = float(box["quantity"] or 0) - float(allocated or 0)
            if remaining <= 0:
                continue
            raw_q = p.get("quantity")
            try:
                take = remaining if raw_q is None else float(raw_q)
            except (TypeError, ValueError):
                continue
            if take <= 0:
                continue
            take = min(take, remaining)
            cur = conn.execute(
                "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, allocated_by, kind) "
                "VALUES (?,?,?,?,?,?)",
                (bid, order_thread_id, take, now, by or "", kind),
            )
            out.append({
                "allocation_id": cur.lastrowid, "box_id": bid, "box_code": box["box_code"],
                "product_code": box["product_code"], "quantity": take, "mfg_date": box.get("mfg_date"),
            })
    return out


def fifo_consume(conn, ref_thread_id, needs, *, by=None) -> list[dict]:
    """Tiêu hao nguyên liệu (FIFO) khi sản xuất. needs=[{code, amount}] — mỗi mã lấy từ
    thùng CŨ NHẤT (created_at) còn hàng cho đủ amount (thùng cuối lấy 1 phần). Ghi
    allocation kind='production', ref_thread_id = phiếu SX. Trả tóm tắt tiêu hao/thiếu.
    """
    summary: list[dict] = []
    for nd in needs:
        code = str(nd.get("code") or "").strip().upper()
        need = float(nd.get("amount") or 0)
        if not code or need <= 0:
            continue
        # thùng còn hàng của nguyên liệu, cũ nhất trước
        rows = conn.execute(
            "SELECT b.id, b.box_code, b.quantity - COALESCE("
            "(SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS rem "
            "FROM inventory_boxes b WHERE b.product_code = ? AND (b.disabled IS NULL OR b.disabled = 0) "
            "ORDER BY b.created_at, b.box_code",
            (code,),
        ).fetchall()
        left = need
        picks = []
        for r in rows:
            if left <= 0:
                break
            rem = float(r[2] or 0)
            if rem <= 0:
                continue
            take = min(rem, left)
            picks.append({"box_id": r[0], "quantity": take})
            left -= take
        done = allocate_picks(conn, picks, ref_thread_id, by=by, kind="production")
        consumed = sum(d["quantity"] for d in done)
        summary.append({
            "code": code, "need": need, "consumed": consumed,
            "shortfall": max(0.0, need - consumed), "picks": done,
        })
    return summary


def release_production_consumption(conn, ref_thread_id) -> int:
    """Hoàn lại nguyên liệu đã tiêu hao cho 1 phiếu SX (xoá allocation kind='production')."""
    with transaction(conn):
        cur = conn.execute(
            "DELETE FROM box_allocations WHERE order_thread_id = ? AND kind = 'production'",
            (ref_thread_id,),
        )
        return cur.rowcount


def list_order_allocations(conn, order_thread_id, *, kind="order") -> list[dict]:
    """Các phần thùng đã xuất cho 1 đơn (kèm info thùng + còn lại của thùng).
    kind='production' → tiêu hao nguyên liệu của 1 phiếu SX."""
    rows = conn.execute(
        "SELECT a.id AS allocation_id, a.quantity AS quantity, a.allocated_by, a.allocated_at, a.kind, "
        "b.id AS box_id, b.box_code, b.product_code, b.quantity AS box_quantity, b.mfg_date, "
        "(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS box_remaining "
        "FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id "
        "WHERE a.order_thread_id = ? AND COALESCE(a.kind,'order') = ? ORDER BY b.box_code",
        (order_thread_id, kind),
    ).fetchall()
    return [dict(r) for r in rows]


def list_box_allocations(conn, box_id) -> list[dict]:
    """Các đơn/phiếu mà 1 thùng đã xuất cho (breakdown cho trang chi tiết thùng)."""
    rows = conn.execute(
        "SELECT id AS allocation_id, order_thread_id, quantity, allocated_by, allocated_at, COALESCE(kind,'order') AS kind "
        "FROM box_allocations WHERE box_id = ? ORDER BY id",
        (box_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_allocation(conn, allocation_id) -> dict | None:
    row = conn.execute("SELECT * FROM box_allocations WHERE id = ?", (allocation_id,)).fetchone()
    return dict(row) if row else None


def delete_allocation(conn, allocation_id) -> bool:
    """Thu hồi 1 phần thùng khỏi đơn (xoá dòng allocation)."""
    with transaction(conn):
        conn.execute("DELETE FROM box_allocations WHERE id = ?", (allocation_id,))
    return True
