"""Nhập KHO hàng mua về từ phiếu NHẬP HÀNG — orchestration thuần (thùng mới / thùng có sẵn).

Không HTTP/realtime — chỉ thao tác store trong 1 connection để route gọi + unit-test
(tests/test_purchase_goods.py). Nối: inventory_store.queries (add_boxes),
inventory_store.allocations (receive_purchase_stock), purchase_store (claim/set_goods_result).

Hai cách nhập mỗi dòng hàng mua (khác hàng trả: KHÔNG có xuất hủy):
  • restock_new      — TẠO thùng mới (chọn vị trí/đơn vị), thùng gắn source_purchase_id.
  • restock_existing — nhập vào 1 thùng CÓ SẴN: allocation ÂM kind='purchase_in'
                       → remaining tăng, quantity gốc thùng GIỮ NGUYÊN.
Số lượng lấy từ disposition (số THỰC NHẬN — có thể lệch số trên phiếu vì thiếu/vỡ).
"""
from __future__ import annotations


def apply_purchase_receipt(conn, purchase_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Áp dụng từng disposition cho hàng của phiếu nhập purchase_id.

    dispositions = [{sp, quantity, action, box_id?, place_id?, unit_id?}].
    Trả (extra, None) với extra = {result, touched_boxes, supplier_id},
    hoặc (None, 'not_found'|'already'). Dòng không hợp lệ (thiếu mã/số ≤ 0/thùng
    không tồn tại) bị BỎ QUA lặng, không làm hỏng cả lô. Mã ngoài danh mục vẫn
    tạo thùng được (như hàng trả — kho pool theo product_code)."""
    from inventory_store.queries import add_boxes, get_box
    from inventory_store.allocations import receive_purchase_stock
    from purchase_store import get_purchase, claim_goods_handling, set_goods_result

    p = get_purchase(conn, purchase_id)
    if not p or p.get("deleted_at"):
        return None, "not_found"
    # Giành quyền NGUYÊN TỬ trước khi đụng kho → 2 request đồng thời không double-apply.
    if not claim_goods_handling(conn, purchase_id, by=actor):
        return None, "already"

    result: dict = {"restocked_existing": [], "restocked_new": []}
    touched_boxes: list[int] = []
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
            receive_purchase_stock(conn, box_id, q, purchase_id, by=actor)
            touched_boxes.append(box_id)
            result["restocked_existing"].append(
                {"sp": code, "quantity": q, "box_id": box_id, "box_code": box.get("box_code")})
        elif action == "restock_new":
            try:
                boxes = add_boxes(conn, code, [q], source_purchase_id=purchase_id,
                                  place_id=disp.get("place_id"), unit_id=disp.get("unit_id"),
                                  by=actor, note=f"Nhập hàng NCC (phiếu nhập #{purchase_id})")
            except ValueError:
                boxes = []
            if boxes:
                touched_boxes.append(boxes[0]["id"])
                result["restocked_new"].append(
                    {"sp": code, "quantity": q, "box_id": boxes[0]["id"], "box_code": boxes[0]["box_code"]})

    set_goods_result(conn, purchase_id, result)
    return {"result": result, "touched_boxes": touched_boxes,
            "supplier_id": p.get("supplier_id")}, None
