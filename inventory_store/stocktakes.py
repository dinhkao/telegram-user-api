"""Phiếu kiểm kho theo vị trí — snapshot tồn từng thùng, không tự điều chỉnh kho.

Mỗi vị trí chỉ có tối đa một phiếu nháp. Số hệ thống được chụp cố định lúc tạo;
mọi báo cáo chênh lệch vì vậy vẫn đúng dù kho tiếp tục phát sinh nhập/xuất.
"""
from __future__ import annotations

from utils.db import transaction


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


def _row(conn, stocktake_id: int):
    return conn.execute(
        "SELECT * FROM inventory_stocktakes WHERE id = ?", (stocktake_id,)
    ).fetchone()


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
    out["items"] = items
    out["summary"] = {
        "box_count": len(items),
        "counted_count": counted,
        "deviation_count": deviations,
        "expected_total": expected_total,
        "actual_total": actual_total if counted else None,
        "difference_total": (actual_total - expected_total) if counted == len(items) else None,
    }
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
              AND b.quantity - COALESCE(a.qty, 0) > 0.000000001
            ORDER BY COALESCE(p.code, b.product_code), b.box_code
            """,
            (sid, place_id),
        )
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
        valid_ids = {int(r[0]) for r in conn.execute(
            "SELECT id FROM inventory_stocktake_items WHERE stocktake_id = ?", (stocktake_id,)
        ).fetchall()}
        for raw in counts:
            try:
                item_id = int(raw.get("id"))
                actual_raw = raw.get("actual_quantity")
                actual = None if actual_raw is None or actual_raw == "" else float(actual_raw)
            except (TypeError, ValueError, AttributeError):
                return None, "invalid"
            if item_id not in valid_ids or (actual is not None and actual < 0):
                return None, "invalid"
            conn.execute(
                "UPDATE inventory_stocktake_items SET actual_quantity = ?, note = ? "
                "WHERE id = ? AND stocktake_id = ?",
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
        conn.execute(
            "UPDATE inventory_stocktakes SET status = 'completed', completed_at = datetime('now'), "
            "completed_by = ?, updated_at = datetime('now'), updated_by = ?, "
            "note = COALESCE(?, note) WHERE id = ?",
            (actor, actor, None if note is None else str(note).strip(), stocktake_id),
        )
        return _payload(conn, stocktake_id), None
