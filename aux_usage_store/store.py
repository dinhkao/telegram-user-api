"""Bảng + thao tác sổ ghi định mức NL phụ (aux_usage_ledger). IO + transaction.

1 bản ghi = 1 (thùng thành phẩm × 1 NL phụ): amount = quantity thùng × tỉ lệ công thức
(snapshot ratio lúc ghi). occurred_at = thời điểm tạo thùng (giờ VN). VOID mềm khi xóa
thùng. Idempotent theo (source_box_id, ingredient_id) — ghi 2 lần cùng thùng không
nhân đôi. Nối: recipe_store.list_recipe (aux=True), product_store.resolve_code.
"""
from __future__ import annotations

from utils.db import transaction


def create_aux_usage_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aux_usage_ledger (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            source_thread_id    INTEGER,
            source_box_id       INTEGER NOT NULL,
            output_product_id   INTEGER,
            output_product_code TEXT,
            ingredient_id       INTEGER,
            ingredient_code     TEXT NOT NULL,
            produced_qty        REAL NOT NULL,
            ratio               REAL NOT NULL,
            amount              REAL NOT NULL,
            occurred_at         TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
            voided_at           TEXT,
            voided_by           TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_aux_usage_box_ing "
                 "ON aux_usage_ledger(source_box_id, ingredient_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aux_usage_ing_time "
                 "ON aux_usage_ledger(ingredient_id, occurred_at)")


def record_boxes_aux_usage(conn, boxes: list[dict], product_code: str, *, by: str | None = None) -> int:
    """Ghi định mức NL phụ cho các thùng thành phẩm vừa tạo (KHÔNG trừ kho).

    boxes = [{id, quantity, ...}] (kết quả add_boxes). Với mỗi NL phụ trong công thức
    của product_code, ghi amount = quantity thùng × ratio. Trả số bản ghi đã ghi.
    Bọc trong transaction re-entrant (caller đã mở transaction thì dùng chung)."""
    from recipe_store import list_recipe
    aux_lines = [l for l in list_recipe(conn, product_code, aux=True)]
    if not aux_lines or not boxes:
        return 0
    from product_store import resolve_code
    prod = resolve_code(conn, product_code)
    out_id = prod["id"] if prod else None
    out_code = prod["code"] if prod else str(product_code or "").strip().upper()
    n = 0
    with transaction(conn):
        for box in boxes:
            bid = box.get("id")
            qty = float(box.get("quantity") or 0)
            if not bid or qty <= 0:
                continue
            for ln in aux_lines:
                ratio = float(ln.get("ratio") or 0)
                if ratio <= 0:
                    continue
                amount = round(qty * ratio, 6)
                # Idempotent: ghi lại cùng (thùng, NL) thì cập nhật, không nhân đôi.
                conn.execute(
                    "INSERT INTO aux_usage_ledger (source_thread_id, source_box_id, "
                    "output_product_id, output_product_code, ingredient_id, ingredient_code, "
                    "produced_qty, ratio, amount) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source_box_id, ingredient_id) DO UPDATE SET "
                    "produced_qty=excluded.produced_qty, ratio=excluded.ratio, "
                    "amount=excluded.amount, voided_at=NULL, voided_by=NULL",
                    (box.get("source_thread_id"), int(bid), out_id, out_code,
                     ln.get("ingredient_id"), ln.get("ingredient_code"),
                     qty, ratio, amount),
                )
                n += 1
    return n


def void_box_aux_usage(conn, box_id: int, *, by: str | None = None) -> int:
    """VOID mềm mọi bản ghi định mức của 1 thùng thành phẩm (khi xóa/rã thùng).
    Giữ dòng, chỉ đóng dấu voided_at → không còn tính vào đối chiếu. Trả số dòng void."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE aux_usage_ledger SET voided_at = datetime('now', '+7 hours'), voided_by = ? "
            "WHERE source_box_id = ? AND voided_at IS NULL",
            (by or "", int(box_id)),
        )
    return cur.rowcount


def aux_usage_by_ingredient(conn, t0: str, t1: str) -> dict[int, float]:
    """Tổng định mức đã ghi (chưa void) theo ingredient_id trong khoảng (t0, t1].
    Mốc chuẩn hóa epoch (occurred_at giờ VN). Trả {ingredient_id: amount}."""
    rows = conn.execute(
        "SELECT ingredient_id, SUM(amount) AS amt FROM aux_usage_ledger "
        "WHERE voided_at IS NULL AND ingredient_id IS NOT NULL "
        "AND strftime('%s', occurred_at) > strftime('%s', ?) "
        "AND strftime('%s', occurred_at) <= strftime('%s', ?) "
        "GROUP BY ingredient_id",
        (t0, t1),
    ).fetchall()
    return {int(r["ingredient_id"]): float(r["amt"] or 0) for r in rows}
