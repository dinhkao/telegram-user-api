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


def undo_purchase_receipt(conn, purchase_id: int) -> tuple[dict | None, str | None]:
    """HỦY CHỐT nhập kho của 1 phiếu nhập (admin) — hoàn tác toàn bộ hoặc KHÔNG gì cả.

    Điều kiện: hàng nhập vào kho CHƯA ĐƯỢC DÙNG. Cụ thể:
      • thùng MỚI tạo từ phiếu: chưa có allocation nào (chưa xuất đơn/hủy/chuyển);
      • thùng CÓ SẴN đã cộng thêm: remaining hiện tại ≥ số đã cộng (phần cộng thêm
        chưa bị tiêu vào đâu) — gỡ allocation purchase_in xong remaining không âm.
    Vi phạm 1 dòng → trả lỗi, KHÔNG hoàn dòng nào. Thùng đã bị admin xoá hẳn → bỏ qua.
    Xong: xoá thùng mới, gỡ allocation purchase_in, clear goods_handled_* → phiếu
    mở khoá sửa + nhập kho lại được. Trả (info, None) hoặc (None, lỗi VN)."""
    from inventory_store.queries import get_box, delete_box
    from inventory_store.allocations import list_box_allocations
    from purchase_store import get_purchase, clear_goods_handling

    p = get_purchase(conn, purchase_id)
    if not p or p.get("deleted_at"):
        return None, "Không tìm thấy phiếu nhập"
    gr = p.get("goods_result")
    if not p.get("goods_handled_at"):
        return None, "Phiếu chưa chốt nhập kho"

    new_entries = list((gr or {}).get("restocked_new") or [])
    exist_entries = list((gr or {}).get("restocked_existing") or [])
    # ── Kiểm TRƯỚC toàn bộ, không đụng DB — all-or-nothing ──
    to_delete: list[int] = []          # thùng mới sẽ xoá
    to_unalloc: list[int] = []         # allocation purchase_in sẽ gỡ
    for e in new_entries:
        box = get_box(conn, e.get("box_id"))
        if not box:
            continue                    # admin đã xoá thùng → coi như xử lý rồi
        allocs = list_box_allocations(conn, box["id"])
        used = [a for a in allocs if (a.get("kind") or "order") != "purchase_in"]
        if used:
            return None, f"Thùng {box.get('box_code')} ({e.get('sp')}) đã được dùng ({len(used)} lần xuất/chuyển) — không hủy chốt được"
        to_unalloc += [a["allocation_id"] for a in allocs if (a.get("kind") or "") == "purchase_in"]
        to_delete.append(box["id"])
    for e in exist_entries:
        box = get_box(conn, e.get("box_id"))
        if not box:
            continue
        all_allocs = list_box_allocations(conn, box["id"])
        allocs = [a for a in all_allocs
                  if (a.get("kind") or "") == "purchase_in" and a.get("order_thread_id") == purchase_id]
        q_in = -sum(float(a.get("quantity") or 0) for a in allocs)   # dòng purchase_in quantity ÂM
        remaining = float(box.get("quantity") or 0) - sum(float(a.get("quantity") or 0) for a in all_allocs)
        if remaining < q_in - 1e-9:
            return None, (f"Thùng {box.get('box_code')} ({e.get('sp')}) đã dùng một phần hàng nhập "
                          f"(còn {remaining:g} < {q_in:g} đã cộng) — không hủy chốt được")
        to_unalloc += [a["allocation_id"] for a in allocs]
    # ── Áp dụng ──
    for aid in to_unalloc:
        conn.execute("DELETE FROM box_allocations WHERE id = ?", (aid,))
    for bid in to_delete:
        delete_box(conn, bid)
    conn.commit()
    clear_goods_handling(conn, purchase_id)
    return {"deleted_boxes": to_delete, "removed_allocations": len(to_unalloc),
            "supplier_id": p.get("supplier_id")}, None


def attach_purchase_boxes(conn, row: dict | None) -> dict | None:
    """Gắn row['boxes'] = info ĐẦY ĐỦ (kèm remaining) của các thùng phiếu đã nhập
    kho — trang chi tiết phiếu vẽ Ô THÙNG (BoxLabelGrid) như trong đơn hàng.
    Chỉ đọc; thùng đã bị xoá hẳn thì không có trong list (đã có cờ box_deleted)."""
    gr = (row or {}).get("goods_result")
    if not row or not gr:
        return row
    from inventory_store.queries import get_box
    from inventory_store.allocations import list_box_allocations
    boxes, seen = [], set()
    for e in list(gr.get("restocked_new") or []) + list(gr.get("restocked_existing") or []):
        bid = e.get("box_id")
        if not bid or bid in seen:
            continue
        seen.add(bid)
        b = get_box(conn, bid)
        if not b:
            continue
        b["remaining"] = float(b.get("quantity") or 0) - sum(
            float(a.get("quantity") or 0) for a in list_box_allocations(conn, bid))
        boxes.append(b)
    if boxes:
        row["boxes"] = boxes
    return row


def mark_deleted_boxes(conn, row: dict | None) -> dict | None:
    """Gắn box_deleted=True cho các entry goods_result mà thùng đã bị admin XOÁ HẲN
    khỏi kho (delete_box là hard-delete) — trang chi tiết phiếu hiện 'đã xoá' thay
    vì link chết. Chỉ đọc, không sửa DB (goods_result là snapshot lịch sử)."""
    gr = (row or {}).get("goods_result")
    if not row or not gr:
        return row
    entries = list(gr.get("restocked_existing") or []) + list(gr.get("restocked_new") or [])
    ids = [e.get("box_id") for e in entries if e.get("box_id")]
    if not ids:
        return row
    q = ",".join("?" for _ in ids)
    alive = {r[0] for r in conn.execute(
        f"SELECT id FROM inventory_boxes WHERE id IN ({q})", ids).fetchall()}
    for e in entries:   # e là reference vào dict trong row → gắn cờ tại chỗ
        if e.get("box_id") and e["box_id"] not in alive:
            e["box_deleted"] = True
    return row
