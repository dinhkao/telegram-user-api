"""ÁP DỤNG chênh lệch KIỂM KHO vào kho thực tế — tạo phiếu điều chỉnh từng thùng lệch.

Tách khỏi stocktakes.py (trần 400 dòng). ĐÚNG LOGIC, KHÔNG SAI SÓT:
  • chỉ phiếu ĐÃ CHỐT (số đếm cố định) và áp đúng 1 LẦN (applied_at — check trong
    cùng transaction ⇒ 2 request đồng thời không double-apply);
  • áp theo DELTA (số đếm − sổ sách lúc chụp), KHÔNG ép remaining = số đếm: kho có
    thể đã biến động HỢP LỆ sau khi chốt (xuất đơn/nhập hàng) — các biến động đó có
    sổ riêng, delta đo tại thời điểm đếm cộng dồn vẫn đúng;
  • ALL-OR-NOTHING: kiểm TRƯỚC toàn bộ (thùng đã xoá / tồn sau điều chỉnh âm →
    trả lỗi, chưa ghi gì) rồi mới ghi, tất cả trong 1 transaction.
Nối: inventory_store.stocktakes (_row/_payload), inventory_store.adjustments
(insert_adjustment — allocation kind='adjustment'). API: server_app/stocktake_routes.
"""
from __future__ import annotations

import json

from utils.db import transaction

_EPS = 1e-6


def apply_stocktake(conn, stocktake_id: int, *, actor: str | None = None) -> tuple[dict | None, str | None]:
    """Trả (payload, None) hoặc (None, lỗi). Lỗi mã: 'not_found'|'not_completed'|
    'already'; lỗi text VN = thùng cụ thể không áp được (client hiện thẳng)."""
    from inventory_store.adjustments import _box_remaining, insert_adjustment
    from inventory_store.stocktakes import _payload, _row, create_stocktake_tables
    create_stocktake_tables(conn)
    with transaction(conn):
        head = _row(conn, stocktake_id)
        if not head:
            return None, "not_found"
        if head["status"] != "completed":
            return None, "not_completed"
        if head["applied_at"]:
            return None, "already"
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM inventory_stocktake_items WHERE stocktake_id = ? ORDER BY product_code, box_code",
            (stocktake_id,)).fetchall()]
        lech = [it for it in items if it.get("actual_quantity") is not None
                and abs(float(it["actual_quantity"]) - float(it["expected_quantity"] or 0)) > _EPS]
        # ── Kiểm TRƯỚC toàn bộ (chưa ghi gì) ──
        plan = []
        for it in lech:
            delta = float(it["actual_quantity"]) - float(it["expected_quantity"] or 0)
            box, rem = _box_remaining(conn, int(it["box_id"]))
            if not box:
                return None, f"Thùng {it['box_code']} ({it['product_code']}) đã bị xoá khỏi kho — không áp được"
            if box["disabled"]:
                return None, (f"Thùng {it['box_code']} ({it['product_code']}) đã bị vô hiệu hoá — "
                              f"kích hoạt lại trước khi áp (tránh cộng tồn vào thùng đã tắt).")
            if rem + delta < -_EPS:
                return None, (f"Thùng {it['box_code']} ({it['product_code']}): điều chỉnh {delta:+g} "
                              f"nhưng hiện chỉ còn {rem:g} — tồn sẽ âm. Kiểm lại trước khi áp.")
            plan.append((it, delta))
        # ── Áp dụng ──
        reason = f"Kiểm kho {head['place_name']} — phiếu #{stocktake_id}"
        applied = []
        for it, delta in plan:
            adj, err = insert_adjustment(conn, int(it["box_id"]), delta=delta, reason=reason,
                                         by=actor or "", source="stocktake", stocktake_id=stocktake_id)
            if err:   # phòng hờ — raise để transaction rollback TOÀN BỘ
                raise ValueError(err)
            applied.append({"box_id": it["box_id"], "box_code": it["box_code"],
                            "product_code": it["product_code"], "delta": round(delta, 3),
                            "adjustment_id": adj["id"]})
        result = {"adjusted": applied, "equal_count": len(items) - len(lech)}
        conn.execute(
            "UPDATE inventory_stocktakes SET applied_at = datetime('now', '+7 hours'), applied_by = ?, "
            "applied_result = ? WHERE id = ? AND applied_at IS NULL",
            (actor, json.dumps(result, ensure_ascii=False), stocktake_id))
        return _payload(conn, stocktake_id), None
