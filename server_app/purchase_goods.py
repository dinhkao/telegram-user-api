"""Nhập KHO hàng mua về từ phiếu NHẬP HÀNG — orchestration thuần (thùng mới / thùng có sẵn).

Không HTTP/realtime — chỉ thao tác store trong 1 connection để route gọi + unit-test
(tests/test_purchase_goods.py). Nối: inventory_store.queries (add_boxes),
inventory_store.allocations (receive_purchase_stock), purchase_store (claim/set_goods_result).

Hai cách nhập mỗi dòng hàng mua (khác hàng trả: KHÔNG có xuất hủy):
  • restock_new      — TẠO N thùng GIỐNG NHAU (như nhập thùng phiếu SX): `count` =
                       số thùng, `quantity` = số hàng trong 1 thùng → tạo count thùng
                       mỗi thùng quantity (chọn vị trí/đơn vị), thùng gắn source_purchase_id.
                       Thiếu `count` → 1 thùng (tương thích ngược).
  • restock_existing — nhập vào 1 thùng CÓ SẴN: allocation ÂM kind='purchase_in'
                       → remaining tăng, quantity gốc thùng GIỮ NGUYÊN.
Số lượng lấy từ disposition (số THỰC NHẬN — có thể lệch số trên phiếu vì thiếu/vỡ).
"""
from __future__ import annotations

import json as _json
from datetime import datetime as _dt, timezone as _tz, timedelta as _td


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — khớp purchase_store._now_vn (định dạng goods_handled_at nhất quán)
    return _dt.now(_tz(_td(hours=7))).isoformat(timespec="seconds")


def apply_purchase_receipt(conn, purchase_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Áp dụng từng disposition cho hàng của phiếu nhập purchase_id.

    dispositions = [{sp, quantity, action, box_id?, place_id?, unit_id?, count?}].
    restock_new: `count` = số thùng (mặc định 1), `quantity` = số hàng / 1 thùng.
    Trả (extra, None) với extra = {result, touched_boxes, supplier_id},
    hoặc (None, 'not_found'|'already'). Dòng không hợp lệ (thiếu mã/số ≤ 0/thùng
    không tồn tại) bị BỎ QUA lặng, không làm hỏng cả lô. Mã ngoài danh mục vẫn
    tạo thùng được (như hàng trả — kho pool theo product_code)."""
    from inventory_store.queries import add_boxes, get_box
    from inventory_store.allocations import receive_purchase_stock
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    # Claim + mọi ghi kho + set_goods_result trong 1 transaction → all-or-nothing.
    # add_boxes/receive_purchase_stock dùng `with transaction` re-entrant (an toàn).
    # claim_goods_handling/set_goods_result commit trần → INLINE SQL của chúng.
    with transaction(conn):
        p = get_purchase(conn, purchase_id)
        if not p or p.get("deleted_at"):
            return None, "not_found"
        # Giành quyền NGUYÊN TỬ (compare-and-set) — 2 request đồng thời không double-apply.
        claimed = conn.execute(
            "UPDATE purchase_slips SET goods_handled_at = ?, goods_handled_by = ? "
            "WHERE id = ? AND goods_handled_at IS NULL",
            (_now_vn(), actor or "", purchase_id))
        if claimed.rowcount != 1:
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
                # count = số thùng giống nhau (như nhập thùng phiếu SX); mỗi thùng q hàng.
                try:
                    count = int(disp.get("count") or 1)
                except (TypeError, ValueError):
                    count = 1
                if count < 1:
                    count = 1
                try:
                    boxes = add_boxes(conn, code, [q] * count, source_purchase_id=purchase_id,
                                      place_id=disp.get("place_id"), unit_id=disp.get("unit_id"),
                                      by=actor, note=f"Nhập hàng NCC (phiếu nhập #{purchase_id})")
                except ValueError:
                    boxes = []
                for bx in boxes:
                    touched_boxes.append(bx["id"])
                    result["restocked_new"].append(
                        {"sp": code, "quantity": q, "box_id": bx["id"], "box_code": bx["box_code"]})

        # inline set_goods_result(conn, purchase_id, result) — tránh bare commit
        conn.execute("UPDATE purchase_slips SET goods_result = ? WHERE id = ?",
                     (_json.dumps(result, ensure_ascii=False), purchase_id))
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
    from inventory_store.queries import get_box
    from inventory_store.allocations import list_box_allocations
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    # Toàn bộ hoàn tác trong 1 transaction (BEGIN IMMEDIATE) → all-or-nothing. Không
    # gọi helper có bare commit (delete_box/list_box_allocations dùng transaction re-entrant,
    # an toàn; clear_goods_handling commit trần nên INLINE SQL của nó).
    with transaction(conn):
        p = get_purchase(conn, purchase_id)
        if not p or p.get("deleted_at"):
            return None, "Không tìm thấy phiếu nhập"
        gr = p.get("goods_result")
        if not p.get("goods_handled_at"):
            return None, "Phiếu chưa chốt nhập kho"

        new_entries = list((gr or {}).get("restocked_new") or [])
        exist_entries = list((gr or {}).get("restocked_existing") or [])
        # ── Kiểm TRƯỚC toàn bộ — all-or-nothing (return trong transaction = rollback) ──
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
            conn.execute("DELETE FROM inventory_boxes WHERE id = ?", (bid,))
        # inline clear_goods_handling(conn, purchase_id) — tránh bare commit cắt transaction
        conn.execute(
            "UPDATE purchase_slips SET goods_handled_at = NULL, goods_handled_by = NULL, goods_result = NULL"
            " WHERE id = ?", (purchase_id,))
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
