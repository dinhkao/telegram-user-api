"""Phiếu NHẬP HÀNG (purchase_slips, app.db) — nhập hàng từ nhà cung cấp.

100% local, KHÔNG dính KiotViet. Flow giống ĐƠN: tạo phiếu (sửa được, văn phòng)
→ xoá = admin (xoá mềm). Hàng hoá DÙNG CHUNG bảng sản phẩm: items JSON
[{sp, sp_id?, sl, price}] — sp_id gắn khi mã resolve được (product_store), giá là
snapshot. Nối: utils.db, supplier_store (JOIN tên NCC).
API: server_app/purchase_routes.py.
"""
from __future__ import annotations

import json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_slips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id  INTEGER NOT NULL,
    items        TEXT    NOT NULL,          -- JSON [{sp, sp_id?, sl, price}]
    total        REAL    NOT NULL,
    note         TEXT,
    created_by   TEXT,
    created_at   TEXT,
    deleted_at   TEXT,
    deleted_by   TEXT
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchase_slips(supplier_id)",
]


def ensure_purchases_schema(conn) -> None:
    # Trong 1 transaction ngoài (caller wrap `with transaction`) thì BỎ QUA: executescript
    # implicit-commit sẽ cắt transaction. Schema đã được ensure TRƯỚC khi mở transaction.
    if conn.in_transaction:
        return
    conn.executescript(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(purchase_slips)")}
    if "payments" not in cols:   # 2026-07-14: trả tiền NCC từ két (JSON list)
        conn.execute("ALTER TABLE purchase_slips ADD COLUMN payments TEXT")
    # 2026-07-16: nhập kho hàng mua về (thùng có sẵn / thùng mới) — như hàng trả
    for name in ("goods_handled_at", "goods_handled_by", "goods_result"):
        if name not in cols:
            conn.execute(f"ALTER TABLE purchase_slips ADD COLUMN {name} TEXT")
    conn.commit()


def _row_to_dict(r) -> dict:
    from purchase_store.payments import _parse, paid_total
    d = dict(r)
    try:
        d["items"] = json.loads(d.get("items") or "[]")
    except (TypeError, ValueError):
        d["items"] = []
    d["payments"] = _parse(d.get("payments"))
    d["paid"] = paid_total(d["payments"])
    if d.get("goods_result"):
        try:
            d["goods_result"] = json.loads(d["goods_result"])
        except (TypeError, ValueError):
            d["goods_result"] = None
    # remaining tính 1 chỗ (Python round) — client hiển thị thẳng, khỏi lệch
    # Math.round(JS) vs round(Python) khi total lẻ
    d["remaining"] = int(round(float(d.get("total") or 0))) - d["paid"]
    return d


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — cùng định dạng return_slips để sort/hiển thị nhất quán
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def add_purchase(conn, supplier_id: int, items: list[dict], total: float, *,
                 note: str = "", by: str = "") -> dict:
    ensure_purchases_schema(conn)
    cur = conn.execute(
        "INSERT INTO purchase_slips (supplier_id, items, total, note, created_by, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (int(supplier_id), json.dumps(items, ensure_ascii=False), float(total),
         note or "", by or "", _now_vn()))
    conn.commit()
    return get_purchase(conn, cur.lastrowid)


def get_purchase(conn, purchase_id: int) -> dict | None:
    ensure_purchases_schema(conn)
    r = conn.execute("SELECT * FROM purchase_slips WHERE id = ?", (purchase_id,)).fetchone()
    return _row_to_dict(r) if r else None


def get_purchase_full(conn, purchase_id: int) -> dict | None:
    """1 phiếu kèm tên NCC (trang chi tiết)."""
    ensure_purchases_schema(conn)
    from supplier_store import ensure_suppliers_schema
    ensure_suppliers_schema(conn)
    r = conn.execute(
        "SELECT p.*, s.name AS supplier_name FROM purchase_slips p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE p.id = ?",
        (purchase_id,)).fetchone()
    return _row_to_dict(r) if r else None


def list_all_purchases(conn, limit: int = 20, offset: int = 0) -> list[dict]:
    """MỌI phiếu nhập mới→cũ, kèm tên NCC — dashboard nhập hàng."""
    ensure_purchases_schema(conn)
    from supplier_store import ensure_suppliers_schema
    ensure_suppliers_schema(conn)
    rows = conn.execute(
        "SELECT p.*, s.name AS supplier_name FROM purchase_slips p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id"
        " WHERE p.deleted_at IS NULL ORDER BY p.created_at DESC, p.id DESC LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_all_purchases(conn) -> int:
    ensure_purchases_schema(conn)
    return int(conn.execute(
        "SELECT COUNT(*) FROM purchase_slips WHERE deleted_at IS NULL").fetchone()[0])


def list_purchases_for_supplier(conn, supplier_id: int) -> list[dict]:
    """Mọi phiếu nhập của 1 NCC mới→cũ (trang chi tiết NCC)."""
    ensure_purchases_schema(conn)
    rows = conn.execute(
        "SELECT * FROM purchase_slips WHERE supplier_id = ? AND deleted_at IS NULL"
        " ORDER BY created_at DESC, id DESC", (int(supplier_id),)).fetchall()
    return [_row_to_dict(r) for r in rows]


def _has_table(conn, name: str) -> bool:
    # bảng kho do inventory_store tạo — DB chưa bật tính năng kho thì guard bỏ qua
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _retained_box_totals(conn, purchase_id: int) -> dict:
    """Hàng ĐÃ NHẬP theo phiếu này còn nằm trong kho: thùng còn sống tạo từ phiếu
    + phần đã cộng vào thùng có sẵn (allocation 'purchase_in'), gộp theo SP —
    key = ('id', products.id) hoặc ('code', MÃ), value = (tổng số, mã hiển thị).
    Dùng cho guard sửa/xoá phiếu (không hạ hàng dưới phần đã nhập)."""
    totals: dict = {}
    if not _has_table(conn, "inventory_boxes"):
        return totals

    def _add(pid_val, code_raw, qty):
        code = str(code_raw or "").strip().upper()
        key = ("id", int(pid_val)) if pid_val is not None else ("code", code)
        cur, _ = totals.get(key, (0.0, code))
        totals[key] = (cur + float(qty or 0), code)

    for r in conn.execute(
            "SELECT product_id, product_code, SUM(quantity) AS q FROM inventory_boxes"
            " WHERE source_purchase_id = ? AND quantity > 0 GROUP BY product_id, product_code",
            (int(purchase_id),)).fetchall():
        _add(r["product_id"], r["product_code"], r["q"])
    if _has_table(conn, "box_allocations"):
        for r in conn.execute(
                "SELECT b.product_id, b.product_code, SUM(-a.quantity) AS q"
                " FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id"
                " WHERE a.kind = 'purchase_in' AND a.order_thread_id = ?"
                " GROUP BY b.product_id, b.product_code", (int(purchase_id),)).fetchall():
            if float(r["q"] or 0) > 0:
                _add(r["product_id"], r["product_code"], r["q"])
    return totals


def _items_totals(conn, items: list[dict]) -> dict:
    """Tổng số hàng (đơn vị gốc) theo SP của items phiếu — cùng key với
    _retained_box_totals để so được với thùng đang giữ. Mã không kèm sp_id được
    resolve qua product_store (cùng cách add_boxes gắn product_id cho thùng)."""
    from product_store import resolve_code
    totals: dict = {}
    for it in items or []:
        code = str((it or {}).get("sp") or "").strip().upper()
        if not code:
            continue
        try:
            qty = float((it or {}).get("sl"))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        if (it or {}).get("unit"):
            try:
                f = float((it or {}).get("unit_factor"))
            except (TypeError, ValueError):
                f = 0.0
            if f > 0:
                qty *= f
        sp_id = (it or {}).get("sp_id")
        if sp_id in (None, ""):
            prod = resolve_code(conn, code)
            sp_id = prod["id"] if prod else None
        key = ("id", int(sp_id)) if sp_id not in (None, "") else ("code", code)
        totals[key] = totals.get(key, 0.0) + qty
    return totals


def update_purchase_items(conn, purchase_id: int, items: list[dict], total: float,
                          note: str, supplier_id: int | None = None) -> tuple[bool, str]:
    """Sửa hàng nhập/ghi chú (văn phòng) — đổi cả NCC nếu truyền supplier_id.
    CHẶN hạ tổng xuống dưới số ĐÃ TRẢ NCC (cùng transaction, tránh race với trả
    tiền đồng thời) — không thì phiếu trả-dư bị che thành 'đã trả đủ'.
    CHẶN sửa khi phiếu đã CHỐT nhập kho (re-check trong transaction — route đã
    check nhưng có thể bị chốt đồng thời giữa 2 bước) và chặn hạ hàng xuống dưới
    số đang nằm trong thùng giữ lại sau hủy chốt (không thì phiếu kẹt, không chốt
    lại được)."""
    from purchase_store.payments import _parse, paid_total
    from utils.db import transaction
    ensure_purchases_schema(conn)
    with transaction(conn):
        r = conn.execute(
            "SELECT payments, supplier_id, goods_handled_at FROM purchase_slips WHERE id = ?",
            (purchase_id,)).fetchone()
        if r and r["goods_handled_at"]:
            return False, "Phiếu đã nhập kho — không sửa hàng được nữa"
        paid = paid_total(_parse(r["payments"])) if r else 0
        if int(round(float(total))) < paid:
            return False, (f"Phiếu đã trả {paid:,}đ — tổng mới không được thấp hơn số đã trả"
                           .replace(",", "."))
        retained = _retained_box_totals(conn, purchase_id)
        if retained:   # chỉ resolve items khi có thùng giữ lại (DB không kho thì bỏ qua)
            new_totals = _items_totals(conn, items)
            for key, (qty, code) in retained.items():
                if qty > new_totals.get(key, 0.0) + 1e-9:
                    return False, (f"Kho đang giữ {qty:g} {code} trong thùng tạo từ phiếu này — "
                                   f"hàng trên phiếu không được thấp hơn (xoá bớt thùng trước)")
        # Đã trả tiền NCC → không được đổi sang NCC khác (các lần trả gắn với NCC cũ
        # sẽ lệch két/công nợ). Muốn đổi thì gỡ hết các lần trả trước.
        cur_sup = r["supplier_id"] if r else None
        if (paid > 0 and supplier_id is not None and cur_sup is not None
                and int(supplier_id) != int(cur_sup)):
            return False, "Phiếu đã trả tiền NCC — không đổi nhà cung cấp được (gỡ các lần trả trước)"
        if supplier_id is not None:
            conn.execute(
                "UPDATE purchase_slips SET items = ?, total = ?, note = ?, supplier_id = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), float(total), note or "", int(supplier_id), purchase_id))
        else:
            conn.execute(
                "UPDATE purchase_slips SET items = ?, total = ?, note = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), float(total), note or "", purchase_id))
    return True, ""


def claim_goods_handling(conn, purchase_id: int, by: str = "") -> bool:
    """GIÀNH quyền nhập kho hàng mua về (compare-and-set nguyên tử) — đặt
    goods_handled_at CHỈ khi còn NULL. False = đã có người nhập (chặn 2 request
    đồng thời double-apply vào kho). Gọi TRƯỚC khi thao tác kho."""
    ensure_purchases_schema(conn)
    cur = conn.execute(
        "UPDATE purchase_slips SET goods_handled_at = ?, goods_handled_by = ? "
        "WHERE id = ? AND goods_handled_at IS NULL",
        (_now_vn(), by or "", purchase_id))
    conn.commit()
    return cur.rowcount == 1


def clear_goods_handling(conn, purchase_id: int) -> bool:
    """Helper cũ: xoá dấu goods_handled_* và toàn bộ goods_result.

    Luồng undo hiện tại ghi inline để giữ snapshot thùng mới, không gọi helper này.
    """
    ensure_purchases_schema(conn)
    conn.execute(
        "UPDATE purchase_slips SET goods_handled_at = NULL, goods_handled_by = NULL, goods_result = NULL"
        " WHERE id = ?", (purchase_id,))
    conn.commit()
    return True


def set_goods_result(conn, purchase_id: int, result: dict) -> bool:
    """Lưu tóm tắt kết quả nhập kho (sau khi đã giành quyền + thao tác xong).
    result = {restocked_existing:[], restocked_new:[], skipped:[]}."""
    ensure_purchases_schema(conn)
    conn.execute("UPDATE purchase_slips SET goods_result = ? WHERE id = ?",
                 (json.dumps(result, ensure_ascii=False), purchase_id))
    conn.commit()
    return True


def batch_draft_status(conn, purchase_ids: list[int]) -> dict[int, bool]:
    """Batch kiểm tra các phiếu nhập có thùng nhập dở chưa (draft receipt).
    Trả {purchase_id: True nếu đã có thùng/allocation nhập dở}.
    Dùng cho dashboard để hiển thị tag 'đang nhập dở'."""
    if not purchase_ids:
        return {}
    if not _has_table(conn, "inventory_boxes"):
        return {pid: False for pid in purchase_ids}

    has_draft: set[int] = set()
    ids = [int(pid) for pid in purchase_ids if pid is not None]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))

    for r in conn.execute(
            f"SELECT DISTINCT source_purchase_id FROM inventory_boxes"
            f" WHERE source_purchase_id IN ({ph}) AND quantity > 0",
            ids).fetchall():
        if r[0] is not None:
            has_draft.add(int(r[0]))

    if _has_table(conn, "box_allocations"):
        for r in conn.execute(
                f"SELECT DISTINCT order_thread_id FROM box_allocations"
                f" WHERE kind = 'purchase_in' AND order_thread_id IN ({ph})",
                ids).fetchall():
            if r[0] is not None:
                has_draft.add(int(r[0]))

    return {pid: pid in has_draft for pid in purchase_ids}


def soft_delete_purchase(conn, purchase_id: int, by: str = "") -> tuple[bool, str]:
    """Xoá mềm phiếu nhập (admin). CHẶN khi kho còn dấu vết nhập theo phiếu: thùng
    tạo từ phiếu (kể cả đang nhập dở / sau hủy chốt) hoặc phần đã cộng vào thùng
    có sẵn — xoá phiếu sẽ mồ côi thùng/allocation, link 'Nguồn' chết. Gỡ/xoá các
    phần đó trước rồi mới xoá phiếu."""
    from utils.db import transaction
    ensure_purchases_schema(conn)
    with transaction(conn):
        n_box = conn.execute(
            "SELECT COUNT(*) FROM inventory_boxes WHERE source_purchase_id = ?",
            (int(purchase_id),)).fetchone()[0] if _has_table(conn, "inventory_boxes") else 0
        n_alloc = conn.execute(
            "SELECT COUNT(*) FROM box_allocations WHERE kind = 'purchase_in' AND order_thread_id = ?",
            (int(purchase_id),)).fetchone()[0] if _has_table(conn, "box_allocations") else 0
        if n_box or n_alloc:
            bits = []
            if n_box:
                bits.append(f"{n_box} thùng tạo từ phiếu")
            if n_alloc:
                bits.append(f"{n_alloc} lần cộng vào thùng có sẵn")
            return False, (f"Kho còn {' và '.join(bits)} — xoá thùng/gỡ dòng nhập "
                           f"trước khi xoá phiếu")
        conn.execute(
            "UPDATE purchase_slips SET deleted_at = datetime('now', '+7 hours'), deleted_by = ?"
            " WHERE id = ? AND deleted_at IS NULL", (by or "", purchase_id))
    return True, ""


from purchase_store.payments import (add_purchase_payment, delete_purchase_payment,  # noqa: E402,F401
                                     paid_total, payments_for_cashbox)
