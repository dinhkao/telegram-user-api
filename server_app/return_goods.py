"""Xử lý HÀNG khách trả về — orchestration thuần (nhập kho / tạo thùng / xuất hủy).

Không HTTP/realtime — chỉ thao tác store trong 1 connection để route gọi + unit-test
(tests/test_return_goods.py). Nối: inventory_store.queries (add_boxes/get_box/update_box),
disposal_store (box-less create_manual_disposal), return_store (mark_goods_handled).

Ba cách xử lý mỗi dòng hàng trả:
  • restock_existing — nhập vào 1 thùng CÓ SẴN: allocation ÂM return_in, remaining tăng, quantity gốc giữ nguyên.
  • restock_new      — TẠO thùng mới cho hàng trả (chọn vị trí/đơn vị).
  • dispose          — gom vào 1 phiếu XUẤT HỦY box-less (chỉ ghi nhận, KHÔNG trừ tồn).
"""
from __future__ import annotations

import json as _json
from datetime import datetime as _dt, timezone as _tz, timedelta as _td


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — khớp return_store claim_goods_handling
    return _dt.now(_tz(_td(hours=7))).isoformat(timespec="seconds")


def apply_goods_dispositions(conn, return_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Áp dụng từng disposition cho hàng trả của phiếu return_id.

    dispositions = [{sp, quantity, action, box_id?, place_id?, unit_id?}].
    Trả (extra, None) với extra = {result, touched_boxes, disposal, customer_key},
    hoặc (None, 'not_found'|'already'). Dòng không hợp lệ (thiếu mã/số ≤ 0/thùng
    không tồn tại) bị BỎ QUA lặng, không làm hỏng cả lô."""
    from inventory_store.queries import add_boxes, get_box
    from inventory_store.allocations import receive_return_stock
    from disposal_store import create_manual_disposal
    from return_store import get_return, ensure_returns_schema
    from utils.db import transaction

    ensure_returns_schema(conn)   # DDL trước khi mở transaction
    # Claim + mọi ghi kho + set_goods_result trong 1 transaction → all-or-nothing.
    # add_boxes/receive_return_stock/create_manual_disposal dùng `with transaction`
    # re-entrant (an toàn). claim_goods_handling/set_goods_result commit trần → INLINE SQL.
    with transaction(conn):
        r = get_return(conn, return_id)
        if not r:
            return None, "not_found"
        # Giành quyền NGUYÊN TỬ (compare-and-set) — 2 request đồng thời không double-apply.
        claimed = conn.execute(
            "UPDATE return_slips SET goods_handled_at = ?, goods_handled_by = ? "
            "WHERE id = ? AND goods_handled_at IS NULL",
            (_now_vn(), actor or "", return_id))
        if claimed.rowcount != 1:
            return None, "already"

        result: dict = {"restocked_existing": [], "restocked_new": [], "disposed": [], "disposal_id": None}
        touched_boxes: list[int] = []
        dispose_items: list[dict] = []
        for disp in dispositions or []:
            action = str(disp.get("action") or "").strip()
            code = str(disp.get("sp") or "").strip().upper()
            try:
                q = float(disp.get("quantity"))
            except (TypeError, ValueError):
                continue
            if not code or q <= 0 or action in ("", "skip"):
                continue
            if action == "restock_existing":
                try:
                    box_id = int(disp.get("box_id"))
                except (TypeError, ValueError):
                    continue
                box = get_box(conn, box_id)
                if not box:
                    continue
                # Ghi allocation ÂM 'return_in' — remaining tăng q, quantity gốc GIỮ NGUYÊN
                # (không thổi phồng boxed_total phiếu SX nguồn). Xem receive_return_stock.
                receive_return_stock(conn, box_id, q, return_id, by=actor)
                touched_boxes.append(box_id)
                result["restocked_existing"].append(
                    {"sp": code, "quantity": q, "box_id": box_id, "box_code": box.get("box_code")})
            elif action == "restock_new":
                try:
                    boxes = add_boxes(conn, code, [q], place_id=disp.get("place_id"),
                                      unit_id=disp.get("unit_id"), by=actor,
                                      source_return_id=return_id,
                                      note=f"Hàng khách trả (phiếu trả #{return_id})")
                except ValueError:
                    boxes = []
                if boxes:
                    touched_boxes.append(boxes[0]["id"])
                    result["restocked_new"].append(
                        {"sp": code, "quantity": q, "box_id": boxes[0]["id"], "box_code": boxes[0]["box_code"]})
            elif action == "dispose":
                dispose_items.append({"product_code": code, "quantity": q})

        disposal = None
        if dispose_items:
            disposal, _ = create_manual_disposal(
                conn, dispose_items, reason=f"Hàng khách trả — huỷ (phiếu trả #{return_id})",
                by=actor, source_return_id=return_id)
            if disposal:
                result["disposed"] = disposal["items"]
                result["disposal_id"] = disposal["id"]

        # inline set_goods_result(conn, return_id, result) — tránh bare commit
        conn.execute("UPDATE return_slips SET goods_result = ? WHERE id = ?",
                     (_json.dumps(result, ensure_ascii=False), return_id))
    return {"result": result, "touched_boxes": touched_boxes,
            "disposal": disposal, "customer_key": r.get("customer_key")}, None
