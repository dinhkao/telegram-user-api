"""Phiếu kiểm kho theo vị trí — snapshot tồn từng thùng, không tự điều chỉnh kho.

Mỗi vị trí chỉ có tối đa một phiếu nháp. Số hệ thống ("sổ sách") được chụp cố định
lúc tạo. Nhưng nếu kho vị trí đó BIẾN ĐỘNG sau khi tạo (thùng đổi số còn lại, thêm
thùng mới, thùng rời/vô hiệu), con số chụp không còn khớp tồn thực → phiếu bị coi
là LỖI THỜI: `_payload` gắn cờ `stale` (so tồn hiện tại với snapshot), `complete`
bị chặn, người đang kiểm được báo (webapp nghe realtime `inventory_changed`). Cách
gỡ: `resync_stocktake` (cập nhật lại số sổ sách theo tồn hiện tại, GIỮ số đã đếm) —
hoặc `void_stocktake` (huỷ, tạo phiếu mới). Nối: utils.db, box_allocations,
inventory_boxes, products.
"""
from __future__ import annotations

from utils.db import transaction

_STALE_EPS = 1e-6


def create_stocktake_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_stocktakes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id      INTEGER NOT NULL,
            place_name    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'draft',
            note          TEXT,
            captured_at   TEXT NOT NULL DEFAULT (datetime('now')),
            created_by    TEXT,
            updated_at    TEXT,
            updated_by    TEXT,
            completed_at  TEXT,
            completed_by  TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_stocktake_items (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            stocktake_id      INTEGER NOT NULL,
            box_id            INTEGER NOT NULL,
            box_code          TEXT NOT NULL,
            product_code      TEXT NOT NULL,
            product_unit      TEXT,
            expected_quantity REAL NOT NULL DEFAULT 0,
            actual_quantity   REAL,
            note              TEXT,
            UNIQUE(stocktake_id, box_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_place ON inventory_stocktakes(place_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_items_slip ON inventory_stocktake_items(stocktake_id, id)")
    # Chặn hai máy cùng bấm tạo làm sinh hai phiếu nháp cho một kho.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stocktake_one_draft "
        "ON inventory_stocktakes(place_id) WHERE status = 'draft'"
    )
    # DB đã tạo trước khi có thông tin người sửa — migration idempotent.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(inventory_stocktakes)").fetchall()}
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE inventory_stocktakes ADD COLUMN updated_at TEXT")
    if "updated_by" not in cols:
        conn.execute("ALTER TABLE inventory_stocktakes ADD COLUMN updated_by TEXT")
    # 2026-07-16: ÁP DỤNG chênh lệch kiểm kho vào kho (tạo phiếu điều chỉnh) — 1 lần/phiếu
    for name in ("applied_at", "applied_by", "applied_result"):
        if name not in cols:
            conn.execute(f"ALTER TABLE inventory_stocktakes ADD COLUMN {name} TEXT")
    # 2026-07-17 (docs/plan-don-vi-hang-hoa.md): ĐƠN VỊ BẮT BUỘC khi kiểm (vai 📋) —
    # snapshot (tên, factor) từng dòng lúc tạo/resync + số đếm THÔ (N kiện + M lẻ)
    # để audit đọc đúng thao tác người đếm; actual_quantity vẫn là đơn vị gốc.
    icols = {r[1] for r in conn.execute("PRAGMA table_info(inventory_stocktake_items)").fetchall()}
    for name, typ in (("count_unit_name", "TEXT"), ("count_unit_factor", "REAL"),
                      ("counted_bulk", "REAL"), ("counted_loose", "REAL")):
        if name not in icols:
            conn.execute(f"ALTER TABLE inventory_stocktake_items ADD COLUMN {name} {typ}")


def _row(conn, stocktake_id: int):
    return conn.execute(
        "SELECT * FROM inventory_stocktakes WHERE id = ?", (stocktake_id,)
    ).fetchone()


def _stamp_count_units(conn, stocktake_id: int, *, only_null: bool = False) -> None:
    """Snapshot ĐƠN VỊ KIỂM (vai 📋) cho từng dòng — CỐ ĐỊNH theo thời điểm chụp
    (đổi vai/factor sau không ảnh hưởng phiếu đang kiểm). Chỉ stamp khi factor ≠ 1
    (vai = đơn vị gốc ⇔ hành vi cũ, 1 ô nhập). only_null: chỉ dòng mới (resync)."""
    try:
        from product_store.units import role_by_code
    except Exception:   # DB test không có product_store đầy đủ → bỏ qua
        return
    codes = [r[0] for r in conn.execute(
        "SELECT DISTINCT product_code FROM inventory_stocktake_items WHERE stocktake_id = ?",
        (stocktake_id,)).fetchall()]
    for code in codes:
        try:
            role = role_by_code(conn, code, "stocktake")
        except Exception:
            role = None
        if not role or not role.get("factor") or abs(float(role["factor"]) - 1.0) < 1e-12:
            continue
        sql = ("UPDATE inventory_stocktake_items SET count_unit_name = ?, count_unit_factor = ? "
               "WHERE stocktake_id = ? AND product_code = ?")
        params = [role["name"], float(role["factor"]), stocktake_id, code]
        if only_null:
            sql += " AND count_unit_name IS NULL"
        conn.execute(sql, params)


def _place_includes_empty(conn, place_id: int) -> bool:
    """Kho NGUỒN NL phụ (aux_source) đưa CẢ thùng sổ=0 vào phiếu kiểm — để đếm được
    hàng còn THỰC TẾ dù sổ đã cạn (thùng tem sổ ghi hết nhưng ngoài kho vẫn còn →
    trước đây thùng biến mất khỏi phiếu, không có ô nhập). Kho khác giữ lọc tồn>0
    (toàn hệ có ~600 thùng rỗng, đưa hết vào sẽ loạn phiếu)."""
    try:
        from inventory_store.queries import aux_source_place
        src = aux_source_place(conn)
        return bool(src and int(src["id"]) == int(place_id))
    except Exception:
        return False


def _place_live_state(conn, place_id: int) -> dict[int, dict]:
    """Tồn HIỆN TẠI của vị trí — CÙNG tập & công thức với lúc chụp phiếu (thùng active,
    remaining = quantity − Σ mọi allocation). Kho aux_source đưa cả thùng sổ=0 (xem
    _place_includes_empty), kho khác chỉ tồn>0. Trả {box_id: {box_code, product_code,
    product_unit, remaining}} để so với snapshot phát hiện biến động."""
    keep_empty = 1 if _place_includes_empty(conn, place_id) else 0
    rows = conn.execute(
        """
        WITH alloc AS (
            SELECT box_id, SUM(quantity) AS qty FROM box_allocations GROUP BY box_id
        )
        SELECT b.id AS box_id, b.box_code AS box_code,
               COALESCE(p.code, b.product_code) AS product_code,
               COALESCE(p.unit, 'cây') AS product_unit,
               b.quantity - COALESCE(a.qty, 0) AS remaining
        FROM inventory_boxes b
        LEFT JOIN alloc a ON a.box_id = b.id
        LEFT JOIN products p ON p.id = b.product_id
        WHERE b.place_id = ? AND COALESCE(b.disabled, 0) = 0
          AND (b.quantity - COALESCE(a.qty, 0) > 0.000000001 OR ?)
        """,
        (place_id, keep_empty),
    ).fetchall()
    return {int(r["box_id"]): dict(r) for r in rows}


def _compute_stale(items: list[dict], live: dict[int, dict]) -> dict:
    """So snapshot (items đã chụp) với tồn hiện tại (live) → mô tả biến động.
    added = thùng mới xuất hiện, removed = thùng đã rời/hết, adjusted = đổi số còn lại."""
    captured = {int(it["box_id"]): it for it in items}
    added, removed, adjusted = [], [], []
    for bid, lv in live.items():
        if bid not in captured:
            added.append({
                "box_id": bid, "box_code": lv["box_code"], "product_code": lv["product_code"],
                "remaining": round(float(lv["remaining"] or 0), 3),
            })
    for bid, it in captured.items():
        exp = float(it["expected_quantity"] or 0)
        if bid not in live:
            removed.append({
                "box_id": bid, "box_code": it["box_code"], "product_code": it["product_code"],
                "expected": round(exp, 3),
            })
        else:
            cur = float(live[bid]["remaining"] or 0)
            if abs(cur - exp) > _STALE_EPS:
                adjusted.append({
                    "box_id": bid, "box_code": it["box_code"], "product_code": it["product_code"],
                    "expected": round(exp, 3), "current": round(cur, 3),
                })
    added.sort(key=lambda x: (x["product_code"], x["box_code"]))
    removed.sort(key=lambda x: (x["product_code"], x["box_code"]))
    adjusted.sort(key=lambda x: (x["product_code"], x["box_code"]))
    parts = []
    if added:
        parts.append(f"{len(added)} thùng mới")
    if removed:
        parts.append(f"{len(removed)} thùng đã rời kho")
    if adjusted:
        parts.append(f"{len(adjusted)} thùng đổi số")
    return {
        "changed": bool(added or removed or adjusted),
        "added": added, "removed": removed, "adjusted": adjusted,
        "summary": ", ".join(parts),
    }


def _payload(conn, stocktake_id: int) -> dict | None:
    head = _row(conn, stocktake_id)
    if not head:
        return None
    items = []
    expected_total = actual_total = 0.0
    counted = deviations = 0
    for row in conn.execute(
        "SELECT * FROM inventory_stocktake_items WHERE stocktake_id = ? "
        "ORDER BY product_code, box_code, id", (stocktake_id,)
    ).fetchall():
        item = dict(row)
        expected = float(item.get("expected_quantity") or 0)
        actual_raw = item.get("actual_quantity")
        actual = None if actual_raw is None else float(actual_raw)
        diff = None if actual is None else actual - expected
        item["expected_quantity"] = expected
        item["actual_quantity"] = actual
        item["difference"] = diff
        expected_total += expected
        if actual is not None:
            counted += 1
            actual_total += actual
            if abs(diff or 0) > 1e-9:
                deviations += 1
        items.append(item)
    out = dict(head)
    if out.get("applied_result"):
        import json
        try:
            out["applied_result"] = json.loads(out["applied_result"])
        except (TypeError, ValueError):
            out["applied_result"] = None
    out["items"] = items
    out["summary"] = {
        "box_count": len(items),
        "counted_count": counted,
        "deviation_count": deviations,
        "expected_total": expected_total,
        "actual_total": actual_total if counted else None,
        "difference_total": (actual_total - expected_total) if counted == len(items) else None,
    }
    # Chỉ phiếu ĐANG kiểm mới cần soi biến động — phiếu chốt/huỷ là bản ghi cố định.
    if head["status"] == "draft":
        out["stale"] = _compute_stale(items, _place_live_state(conn, int(head["place_id"])))
    else:
        out["stale"] = {"changed": False, "added": [], "removed": [], "adjusted": [], "summary": ""}
    return out


def create_or_resume_stocktake(conn, place_id: int, *, actor: str | None = None) -> tuple[dict | None, bool]:
    """Tạo snapshot mới, hoặc trả lại phiếu nháp đang kiểm của vị trí."""
    create_stocktake_tables(conn)
    with transaction(conn):
        place = conn.execute("SELECT id, name FROM inventory_places WHERE id = ?", (place_id,)).fetchone()
        if not place:
            return None, False
        existing = conn.execute(
            "SELECT id FROM inventory_stocktakes WHERE place_id = ? AND status = 'draft' "
            "ORDER BY id DESC LIMIT 1", (place_id,)
        ).fetchone()
        if existing:
            return _payload(conn, int(existing["id"])), True

        cur = conn.execute(
            "INSERT INTO inventory_stocktakes (place_id, place_name, created_by, updated_at, updated_by) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            (place_id, place["name"], actor, actor),
        )
        sid = int(cur.lastrowid)
        keep_empty = 1 if _place_includes_empty(conn, place_id) else 0
        conn.execute(
            """
            WITH alloc AS (
                SELECT box_id, SUM(quantity) AS qty
                FROM box_allocations GROUP BY box_id
            )
            INSERT INTO inventory_stocktake_items
                (stocktake_id, box_id, box_code, product_code, product_unit, expected_quantity)
            SELECT ?, b.id, b.box_code, COALESCE(p.code, b.product_code), COALESCE(p.unit, 'cây'),
                   b.quantity - COALESCE(a.qty, 0)
            FROM inventory_boxes b
            LEFT JOIN alloc a ON a.box_id = b.id
            LEFT JOIN products p ON p.id = b.product_id
            WHERE b.place_id = ? AND COALESCE(b.disabled, 0) = 0
              AND (b.quantity - COALESCE(a.qty, 0) > 0.000000001 OR ?)
            ORDER BY COALESCE(p.code, b.product_code), b.box_code
            """,
            (sid, place_id, keep_empty),
        )
        _stamp_count_units(conn, sid)
        return _payload(conn, sid), False


def get_stocktake(conn, stocktake_id: int) -> dict | None:
    create_stocktake_tables(conn)
    return _payload(conn, stocktake_id)


def list_place_stocktakes(conn, place_id: int, limit: int = 8) -> list[dict]:
    create_stocktake_tables(conn)
    rows = conn.execute(
        "SELECT id FROM inventory_stocktakes WHERE place_id = ? ORDER BY id DESC LIMIT ?",
        (place_id, max(1, min(int(limit), 30))),
    ).fetchall()
    return [_payload(conn, int(r["id"])) for r in rows]


def save_stocktake(conn, stocktake_id: int, counts: list[dict], *, actor: str | None = None, note=None) -> tuple[dict | None, str | None]:
    create_stocktake_tables(conn)
    with transaction(conn):
        head = _row(conn, stocktake_id)
        if not head:
            return None, "not_found"
        if head["status"] != "draft":
            return None, "completed"
        valid = {int(r["id"]): dict(r) for r in conn.execute(
            "SELECT id, count_unit_factor FROM inventory_stocktake_items WHERE stocktake_id = ?",
            (stocktake_id,)
        ).fetchall()}
        for raw in counts:
            try:
                item_id = int(raw.get("id"))
            except (TypeError, ValueError, AttributeError):
                return None, "invalid"
            if item_id not in valid:
                return None, "invalid"
            if "counted_bulk" in raw or "counted_loose" in raw:
                # Nhập theo ĐƠN VỊ KIỂM (vai 📋): actual = N kiện × factor + M lẻ;
                # lưu cả số THÔ để audit đọc đúng thao tác. Cả 2 ô trống = chưa đếm.
                f = float(valid[item_id].get("count_unit_factor") or 0)
                if f <= 0:
                    return None, "invalid"
                cb_raw, cl_raw = raw.get("counted_bulk"), raw.get("counted_loose")
                if cb_raw in (None, "") and cl_raw in (None, ""):
                    actual, cb, cl = None, None, None
                else:
                    try:
                        cb = float(cb_raw) if cb_raw not in (None, "") else 0.0
                        cl = float(cl_raw) if cl_raw not in (None, "") else 0.0
                    except (TypeError, ValueError):
                        return None, "invalid"
                    if cb < 0 or cl < 0:
                        return None, "invalid"
                    actual = cb * f + cl
                conn.execute(
                    "UPDATE inventory_stocktake_items SET actual_quantity = ?, counted_bulk = ?, "
                    "counted_loose = ?, note = ? WHERE id = ? AND stocktake_id = ?",
                    (actual, cb, cl, str(raw.get("note") or "").strip(), item_id, stocktake_id),
                )
                continue
            try:
                actual_raw = raw.get("actual_quantity")
                actual = None if actual_raw is None or actual_raw == "" else float(actual_raw)
            except (TypeError, ValueError, AttributeError):
                return None, "invalid"
            if actual is not None and actual < 0:
                return None, "invalid"
            conn.execute(
                "UPDATE inventory_stocktake_items SET actual_quantity = ?, counted_bulk = NULL, "
                "counted_loose = NULL, note = ? WHERE id = ? AND stocktake_id = ?",
                (actual, str(raw.get("note") or "").strip(), item_id, stocktake_id),
            )
        if note is not None:
            conn.execute("UPDATE inventory_stocktakes SET note = ? WHERE id = ?", (str(note).strip(), stocktake_id))
        conn.execute(
            "UPDATE inventory_stocktakes SET updated_at = datetime('now'), updated_by = ? WHERE id = ?",
            (actor, stocktake_id),
        )
        return _payload(conn, stocktake_id), None


def complete_stocktake(conn, stocktake_id: int, *, actor: str | None = None, note=None) -> tuple[dict | None, str | None]:
    create_stocktake_tables(conn)
    with transaction(conn):
        head = _row(conn, stocktake_id)
        if not head:
            return None, "not_found"
        if head["status"] != "draft":
            return _payload(conn, stocktake_id), None
        missing = conn.execute(
            "SELECT COUNT(*) FROM inventory_stocktake_items WHERE stocktake_id = ? "
            "AND actual_quantity IS NULL", (stocktake_id,)
        ).fetchone()[0]
        if missing:
            return None, "incomplete"
        # Kho biến động sau khi chụp → số sổ sách đã lệch, KHÔNG cho chốt (phải resync trước).
        cap = [dict(r) for r in conn.execute(
            "SELECT box_id, box_code, product_code, expected_quantity "
            "FROM inventory_stocktake_items WHERE stocktake_id = ?", (stocktake_id,)
        ).fetchall()]
        if _compute_stale(cap, _place_live_state(conn, int(head["place_id"])))["changed"]:
            return _payload(conn, stocktake_id), "stale"
        conn.execute(
            "UPDATE inventory_stocktakes SET status = 'completed', completed_at = datetime('now'), "
            "completed_by = ?, updated_at = datetime('now'), updated_by = ?, "
            "note = COALESCE(?, note) WHERE id = ?",
            (actor, actor, None if note is None else str(note).strip(), stocktake_id),
        )
        return _payload(conn, stocktake_id), None


def resync_stocktake(conn, stocktake_id: int, *, actor: str | None = None) -> tuple[dict | None, str | None]:
    """Cập nhật lại số sổ sách của phiếu nháp theo tồn HIỆN TẠI (gỡ cờ lỗi thời).

    GIỮ số đã đếm (actual_quantity) + ghi chú của các thùng còn trong kho; cập nhật
    expected_quantity theo remaining hiện tại; thêm dòng cho thùng mới (actual NULL);
    xoá dòng của thùng đã rời/hết. Không đụng tới kho — chỉ đồng bộ ảnh chụp."""
    create_stocktake_tables(conn)
    with transaction(conn):
        head = _row(conn, stocktake_id)
        if not head:
            return None, "not_found"
        if head["status"] != "draft":
            return None, "completed"
        live = _place_live_state(conn, int(head["place_id"]))
        existing = {int(r["box_id"]): dict(r) for r in conn.execute(
            "SELECT id, box_id FROM inventory_stocktake_items WHERE stocktake_id = ?", (stocktake_id,)
        ).fetchall()}
        for bid, it in existing.items():
            lv = live.get(bid)
            if lv is None:
                conn.execute("DELETE FROM inventory_stocktake_items WHERE id = ?", (it["id"],))
            else:
                conn.execute(
                    "UPDATE inventory_stocktake_items SET expected_quantity = ?, box_code = ?, "
                    "product_code = ?, product_unit = ? WHERE id = ?",
                    (float(lv["remaining"] or 0), lv["box_code"], lv["product_code"], lv["product_unit"], it["id"]),
                )
        for bid, lv in live.items():
            if bid not in existing:
                conn.execute(
                    "INSERT INTO inventory_stocktake_items "
                    "(stocktake_id, box_id, box_code, product_code, product_unit, expected_quantity) "
                    "VALUES (?,?,?,?,?,?)",
                    (stocktake_id, bid, lv["box_code"], lv["product_code"], lv["product_unit"], float(lv["remaining"] or 0)),
                )
        _stamp_count_units(conn, stocktake_id, only_null=True)   # dòng mới snapshot theo lúc resync
        conn.execute(
            "UPDATE inventory_stocktakes SET updated_at = datetime('now'), updated_by = ? WHERE id = ?",
            (actor, stocktake_id),
        )
        return _payload(conn, stocktake_id), None


def void_stocktake(conn, stocktake_id: int, *, actor: str | None = None) -> tuple[dict | None, str | None]:
    """Huỷ phiếu nháp (status='voided') — số đã kiểm bị bỏ, giải phóng vị trí cho phiếu
    mới (unique draft index chỉ chặn status='draft'). Không huỷ được phiếu đã chốt."""
    create_stocktake_tables(conn)
    with transaction(conn):
        head = _row(conn, stocktake_id)
        if not head:
            return None, "not_found"
        if head["status"] == "completed":
            return None, "completed"
        if head["status"] == "voided":
            return _payload(conn, stocktake_id), None
        conn.execute(
            "UPDATE inventory_stocktakes SET status = 'voided', updated_at = datetime('now'), "
            "updated_by = ? WHERE id = ?",
            (actor, stocktake_id),
        )
        return _payload(conn, stocktake_id), None
