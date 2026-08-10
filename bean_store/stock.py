"""TỒN kho đậu — cộng dồn `bean_moves` của các phiếu CÒN SỐNG (không có bảng tồn
riêng, nên xoá phiếu là tồn tự đúng). Dùng bởi bean_store.slips (guard tồn âm) và
server_app.bean_routes (dashboard). Ghép bảng đọc = bean_store.domain.build_stock_table.
"""
from __future__ import annotations

from .domain import round_qty

_SUM = (
    "SELECT m.bean_id AS bean_id, m.place_id AS place_id, SUM(m.delta) AS qty "
    "FROM bean_moves m JOIN bean_slips s ON s.id = m.slip_id "
    "WHERE s.deleted_at IS NULL"
)


def stock_cells(conn) -> list[dict]:
    """Tồn từng ô (loại đậu × kho) — chỉ ô khác 0."""
    rows = conn.execute(_SUM + " GROUP BY m.bean_id, m.place_id").fetchall()
    out = [{"bean_id": int(r["bean_id"]), "place_id": int(r["place_id"]),
            "qty": round_qty(r["qty"])} for r in rows]
    return [c for c in out if c["qty"]]


def stock_of(conn, bean_id, place_id) -> float:
    """Tồn hiện tại của 1 loại đậu ở 1 kho (0 nếu chưa có biến động nào)."""
    row = conn.execute(
        _SUM + " AND m.bean_id = ? AND m.place_id = ?", (bean_id, place_id)
    ).fetchone()
    return round_qty((row["qty"] if row else 0) or 0)


def stock_by_bean(conn) -> dict[int, float]:
    """Tồn TỔNG mọi kho theo loại đậu — {bean_id: qty}."""
    rows = conn.execute(_SUM + " GROUP BY m.bean_id").fetchall()
    return {int(r["bean_id"]): round_qty(r["qty"]) for r in rows}
