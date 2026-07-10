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
            row = conn.execute(
                "SELECT b.*, COALESCE(pr.code, b.product_code) AS product_code_live "
                "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
                "WHERE b.id = ?", (bid,)).fetchone()
            if not row:
                continue
            box = dict(row)
            box["product_code"] = box.pop("product_code_live") or box.get("product_code")
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
    from .queries import _pid_filter
    summary: list[dict] = []
    for nd in needs:
        code = str(nd.get("code") or "").strip().upper()
        need = float(nd.get("amount") or 0)
        if not code or need <= 0:
            continue
        # thùng còn hàng của nguyên liệu, cũ nhất trước (lọc theo product_id — nhận cả mã cũ)
        frag, ps = _pid_filter(conn, code)
        rows = conn.execute(
            "SELECT b.id, b.box_code, b.quantity - COALESCE("
            "(SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0) AS rem "
            f"FROM inventory_boxes b WHERE {frag} AND (b.disabled IS NULL OR b.disabled = 0) "
            "ORDER BY b.created_at, b.box_code",
            ps,
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


def release_production_amount(conn, ref_thread_id, product_code, amount) -> tuple[float, list[dict]]:
    """Hoàn lại `amount` nguyên liệu (mã product_code) đã tiêu cho 1 phiếu SX — dùng
    khi XOÁ 1 thùng thành phẩm của phiếu đóng gói (hoàn phần NL tương ứng thùng đó,
    ratio × số cây). Gỡ allocation kind='production' MỚI NHẤT trước (LIFO); dòng
    cuối gỡ 1 phần (giảm quantity). Trả (tổng đã hoàn — kẹp theo tổng đã tiêu,
    chi tiết [{box_id, box_code, amount}] từng thùng NL nhận lại)."""
    from .queries import _pid_filter
    code = str(product_code or "").strip().upper()
    left = float(amount or 0)
    if not code or left <= 0:
        return 0.0, []
    released = 0.0
    details: list[dict] = []
    with transaction(conn):
        frag, ps = _pid_filter(conn, code)
        rows = conn.execute(
            "SELECT a.id, a.quantity, b.id AS box_id, b.box_code FROM box_allocations a "
            "JOIN inventory_boxes b ON b.id = a.box_id "
            f"WHERE a.order_thread_id = ? AND COALESCE(a.kind,'order') = 'production' AND {frag} "
            "ORDER BY a.id DESC",
            (ref_thread_id, *ps),
        ).fetchall()
        for r in rows:
            if left <= 1e-9:
                break
            aid, q = r["id"], float(r["quantity"] or 0)
            take = min(q, left)
            if take >= q - 1e-9:
                conn.execute("DELETE FROM box_allocations WHERE id = ?", (aid,))
            else:
                conn.execute("UPDATE box_allocations SET quantity = quantity - ? WHERE id = ?", (take, aid))
            left -= take
            released += take
            details.append({"box_id": r["box_id"], "box_code": r["box_code"], "amount": round(take, 3)})
    return released, details


def transfer_between_boxes(conn, from_id, to_id, quantity, *, by=None) -> tuple[dict | None, str | None]:
    """Chuyển `quantity` cây từ thùng from → thùng to (BẮT BUỘC cùng mã SP).

    Bút toán KÉP trong box_allocations, ghi CÙNG 1 transaction nên tổng tồn kho
    bảo toàn tuyệt đối (không thể ghi được vế này mà mất vế kia):
      • 'transfer_out' quantity = +q trên thùng nguồn  → remaining nguồn GIẢM q
      • 'transfer_in'  quantity = −q trên thùng đích   → remaining đích TĂNG q
        (mọi công thức remaining = quantity − SUM(allocations) tự đúng với số âm)
    `order_thread_id` = id thùng ĐỐI TÁC (dấu vết 2 chiều). `quantity` gốc của cả
    2 thùng KHÔNG đổi → boxed_total phiếu SX nguồn không lệch. Thùng còn dòng
    transfer bị chặn xoá (guard sẵn có) nên lịch sử không mất.
    Trả (result, None) hoặc (None, lý do lỗi)."""
    try:
        fid, tid = int(from_id), int(to_id)
    except (TypeError, ValueError):
        return None, "Thùng không hợp lệ"
    try:
        q = float(quantity)
    except (TypeError, ValueError):
        return None, "Số lượng không hợp lệ"
    if fid == tid:
        return None, "Thùng nguồn và thùng đích phải khác nhau"
    if q <= 0:
        return None, "Số lượng phải > 0"
    now = _now()
    with transaction(conn):
        rows = {int(r["id"]): dict(r) for r in conn.execute(
            "SELECT * FROM inventory_boxes WHERE id IN (?, ?)", (fid, tid)).fetchall()}
        src, dst = rows.get(fid), rows.get(tid)
        if not src or not dst:
            return None, "Không tìm thấy thùng"
        if src.get("disabled") or dst.get("disabled"):
            return None, "Thùng vô hiệu — kích hoạt lại trước khi chuyển"
        # Cùng SP = cùng product_id (danh tính bất biến); thùng chưa backfill id → so mã
        same = (src.get("product_id") == dst.get("product_id")) if (src.get("product_id") and dst.get("product_id")) \
            else str(src.get("product_code") or "").upper() == str(dst.get("product_code") or "").upper()
        if not same:
            return None, "Hai thùng phải cùng mã sản phẩm"
        allocated = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?", (fid,)
        ).fetchone()[0]
        remaining = float(src["quantity"] or 0) - float(allocated or 0)
        if q > remaining + 1e-9:
            return None, f"Thùng nguồn chỉ còn {remaining:g}"
        conn.execute(
            "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, allocated_by, kind) "
            "VALUES (?,?,?,?,?,?)", (fid, tid, q, now, by or "", "transfer_out"))
        conn.execute(
            "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, allocated_by, kind) "
            "VALUES (?,?,?,?,?,?)", (tid, fid, -q, now, by or "", "transfer_in"))
    return {
        "from_id": fid, "to_id": tid, "quantity": q,
        "from_code": src.get("box_code"), "to_code": dst.get("box_code"),
        "from_remaining": round(remaining - q, 3),
    }, None


def list_order_allocations(conn, order_thread_id, *, kind="order") -> list[dict]:
    """Các phần thùng đã xuất cho 1 đơn (kèm info thùng + còn lại của thùng).
    kind='production' → tiêu hao nguyên liệu của 1 phiếu SX."""
    rows = conn.execute(
        "SELECT a.id AS allocation_id, a.quantity AS quantity, a.allocated_by, a.allocated_at, a.kind, "
        "b.id AS box_id, b.box_code, COALESCE(pr.code, b.product_code) AS product_code, "
        "b.quantity AS box_quantity, b.mfg_date, pl.name AS place_name, "
        "(b.quantity - COALESCE((SELECT SUM(x.quantity) FROM box_allocations x WHERE x.box_id=b.id),0)) AS box_remaining "
        "FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id "
        "LEFT JOIN products pr ON pr.id = b.product_id "
        "LEFT JOIN inventory_places pl ON pl.id = b.place_id "
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
