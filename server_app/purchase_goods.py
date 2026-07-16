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
Số lượng lấy từ disposition (số THỰC NHẬN — có thể thấp hơn số trên phiếu vì thiếu/vỡ,
nhưng server không cho vượt số/mã trên phiếu).
"""
from __future__ import annotations

import json as _json
from datetime import datetime as _dt, timezone as _tz, timedelta as _td


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — khớp purchase_store._now_vn (định dạng goods_handled_at nhất quán)
    return _dt.now(_tz(_td(hours=7))).isoformat(timespec="seconds")


class _ReceiptApplyError(Exception):
    pass


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _product_key(conn, code: str, product_id=None) -> tuple[tuple[str, int | str], str]:
    """Danh tính SP để so phiếu/disposition/thùng: ưu tiên products.id, fallback mã."""
    from product_store import get_product_by_id, resolve_code

    raw = str(code or "").strip().upper()
    prod = None
    if product_id not in (None, ""):
        try:
            prod = get_product_by_id(conn, int(product_id))
        except (TypeError, ValueError):
            prod = None
    if not prod and raw:
        prod = resolve_code(conn, raw)
    if prod:
        return ("id", int(prod["id"])), str(prod["code"] or raw).strip().upper()
    return ("code", raw), raw


def _purchase_item_limits(conn, items: list[dict]) -> tuple[dict[tuple[str, int | str], float], dict[tuple[str, int | str], str]]:
    limits: dict[tuple[str, int | str], float] = {}
    labels: dict[tuple[str, int | str], str] = {}
    for it in items or []:
        code = str((it or {}).get("sp") or "").strip().upper()
        if not code:
            continue
        qty = _float_or_none((it or {}).get("sl"))
        if qty is None or qty <= 0:
            continue
        factor = 1.0
        if (it or {}).get("unit"):
            f = _float_or_none((it or {}).get("unit_factor"))
            if f is not None and f > 0:
                factor = f
        key, live_code = _product_key(conn, code, (it or {}).get("sp_id"))
        limits[key] = limits.get(key, 0.0) + qty * factor
        labels[key] = live_code or code
    return limits, labels


def _optional_fk(conn, table: str, value, label: str) -> tuple[int | None, str | None]:
    if value in (None, ""):
        return None, None
    try:
        ident = int(value)
    except (TypeError, ValueError):
        return None, f"{label} không hợp lệ"
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (ident,)).fetchone():
        return None, f"{label} không tồn tại"
    return ident, None


def _box_remaining(conn, box_id: int, box: dict) -> float:
    used = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?",
        (box_id,),
    ).fetchone()[0]
    return float(box.get("quantity") or 0) - float(used or 0)


def _validate_purchase_dispositions(conn, purchase: dict, dispositions, *,
                                    initial_used: dict[tuple[str, int | str], float] | None = None
                                    ) -> tuple[list[dict], str | None]:
    """Chuẩn hoá và kiểm disposition trước khi claim, để lỗi không chốt phiếu âm thầm."""
    limits, labels = _purchase_item_limits(conn, purchase.get("items") or [])
    used: dict[tuple[str, int | str], float] = dict(initial_used or {})
    for key, qty in used.items():
        if key not in limits or qty > limits[key] + 1e-9:
            return [], (f"Các thùng đang giữ của mã {labels.get(key) or key[1]} vượt số trên phiếu "
                        f"({qty:g} > {limits.get(key, 0):g})")
    valid: list[dict] = []

    for disp in dispositions or []:
        if not isinstance(disp, dict):
            return [], "Dòng nhập kho không hợp lệ"
        action = str(disp.get("action") or "").strip()
        if action in ("", "skip"):
            continue
        if action not in ("restock_existing", "restock_new"):
            return [], "Cách nhập kho không hợp lệ"
        code = str(disp.get("sp") or "").strip().upper()
        if not code:
            return [], "Thiếu mã sản phẩm khi nhập kho"
        q = _float_or_none(disp.get("quantity"))
        if q is None or q <= 0:
            return [], f"Số lượng nhập kho của {code} phải > 0"

        key, live_code = _product_key(conn, code)
        if key not in limits:
            return [], f"Mã {live_code or code} không có trong phiếu nhập"

        row = {"action": action, "sp": live_code or code, "quantity": q}
        if action == "restock_new":
            try:
                count = int(disp.get("count") or 1)
            except (TypeError, ValueError):
                return [], f"Số thùng của {live_code or code} không hợp lệ"
            if count < 1:
                return [], f"Số thùng của {live_code or code} phải >= 1"
            place_id, err = _optional_fk(conn, "inventory_places", disp.get("place_id"), "Vị trí kho")
            if err:
                return [], err
            unit_id, err = _optional_fk(conn, "inventory_units", disp.get("unit_id"), "Đơn vị chứa")
            if err:
                return [], err
            row.update({"count": count, "place_id": place_id, "unit_id": unit_id})
            total = q * count
        else:
            try:
                box_id = int(disp.get("box_id"))
            except (TypeError, ValueError):
                return [], f"Chọn thùng hợp lệ cho {live_code or code}"
            from inventory_store.queries import get_box
            box = get_box(conn, box_id)
            if not box:
                return [], f"Không tìm thấy thùng để nhập {live_code or code}"
            if box.get("disabled"):
                return [], f"Thùng {box.get('box_code')} đã vô hiệu — không nhập thêm được"
            remaining = _box_remaining(conn, box_id, box)
            if remaining <= 1e-9:
                return [], f"Thùng {box.get('box_code')} đã hết hàng — không nhập thêm được"
            box_key, box_code = _product_key(conn, box.get("product_code"), box.get("product_id"))
            if box_key != key:
                return [], f"Thùng {box.get('box_code')} là mã {box_code}, không phải {live_code or code}"
            row.update({"box_id": box_id, "box_code": box.get("box_code")})
            total = q

        if used.get(key, 0.0) + total > limits[key] + 1e-9:
            return [], (f"Mã {labels.get(key) or live_code or code} nhập kho vượt số trên phiếu "
                        f"({used.get(key, 0.0) + total:g} > {limits[key]:g})")
        used[key] = used.get(key, 0.0) + total
        valid.append(row)

    return valid, None


def apply_purchase_receipt(conn, purchase_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Áp dụng từng disposition cho hàng của phiếu nhập purchase_id.

    dispositions = [{sp, quantity, action, box_id?, place_id?, unit_id?, count?}].
    restock_new: `count` = số thùng (mặc định 1), `quantity` = số hàng / 1 thùng.
    Trả (extra, None) với extra = {result, touched_boxes, supplier_id},
    hoặc (None, lỗi). Dòng active không hợp lệ bị chặn trước khi chốt phiếu."""
    from inventory_store.queries import add_boxes, get_box
    from inventory_store.allocations import receive_purchase_stock
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    # Claim + mọi ghi kho + set_goods_result trong 1 transaction → all-or-nothing.
    # add_boxes/receive_purchase_stock dùng `with transaction` re-entrant (an toàn).
    # claim_goods_handling/set_goods_result commit trần → INLINE SQL của chúng.
    try:
        with transaction(conn):
            p = get_purchase(conn, purchase_id)
            if not p or p.get("deleted_at"):
                return None, "not_found"
            # Sau khi hủy chốt, các thùng mới vẫn được giữ nguyên. Chốt lại phải
            # tính chúng vào kết quả và hạn mức để chỉ nhập PHẦN BỔ SUNG.
            retained_new: list[dict] = []
            retained_used: dict[tuple[str, int | str], float] = {}
            rows = conn.execute(
                "SELECT * FROM inventory_boxes WHERE source_purchase_id = ? ORDER BY id",
                (purchase_id,),
            ).fetchall()
            for raw in rows:
                box = dict(raw)
                q = float(box.get("quantity") or 0)
                if q <= 0:
                    continue
                key, code = _product_key(conn, box.get("product_code"), box.get("product_id"))
                retained_used[key] = retained_used.get(key, 0.0) + q
                retained_new.append({
                    "sp": code, "quantity": q, "box_id": box["id"],
                    "box_code": box.get("box_code"),
                })

            valid, err = _validate_purchase_dispositions(
                conn, p, dispositions, initial_used=retained_used)
            if err:
                return None, err
            # Giành quyền NGUYÊN TỬ (compare-and-set) — 2 request đồng thời không double-apply.
            claimed = conn.execute(
                "UPDATE purchase_slips SET goods_handled_at = ?, goods_handled_by = ? "
                "WHERE id = ? AND goods_handled_at IS NULL",
                (_now_vn(), actor or "", purchase_id))
            if claimed.rowcount != 1:
                return None, "already"

            result: dict = {"restocked_existing": [], "restocked_new": retained_new}
            touched_boxes: list[int] = [e["box_id"] for e in retained_new]
            for disp in valid:
                action = disp["action"]
                code = disp["sp"]
                q = float(disp["quantity"])
                if action == "restock_existing":
                    box_id = int(disp["box_id"])
                    if not receive_purchase_stock(conn, box_id, q, purchase_id, by=actor):
                        raise _ReceiptApplyError(f"Không nhập được hàng vào thùng {disp.get('box_code')}")
                    touched_boxes.append(box_id)
                    result["restocked_existing"].append(
                        {"sp": code, "quantity": q, "box_id": box_id, "box_code": disp.get("box_code")})
                elif action == "restock_new":
                    # count = số thùng giống nhau (như nhập thùng phiếu SX); mỗi thùng q hàng.
                    count = int(disp.get("count") or 1)
                    try:
                        boxes = add_boxes(conn, code, [q] * count, source_purchase_id=purchase_id,
                                          place_id=disp.get("place_id"), unit_id=disp.get("unit_id"),
                                          by=actor, note=f"Nhập hàng NCC (phiếu nhập #{purchase_id})")
                    except ValueError:
                        raise _ReceiptApplyError("Không còn số gọi trống để tạo thùng mới")
                    for bx in boxes:
                        touched_boxes.append(bx["id"])
                        result["restocked_new"].append(
                            {"sp": code, "quantity": q, "box_id": bx["id"], "box_code": bx["box_code"]})

            # inline set_goods_result(conn, purchase_id, result) — tránh bare commit
            conn.execute("UPDATE purchase_slips SET goods_result = ? WHERE id = ?",
                         (_json.dumps(result, ensure_ascii=False), purchase_id))
    except _ReceiptApplyError as exc:
        return None, str(exc)
    return {"result": result, "touched_boxes": touched_boxes,
            "supplier_id": p.get("supplier_id")}, None


def undo_purchase_receipt(conn, purchase_id: int) -> tuple[dict | None, str | None]:
    """HỦY CHỐT nhập kho của 1 phiếu nhập (admin) — mở khóa, giữ nguyên thùng mới.

    Điều kiện: hàng nhập vào kho CHƯA ĐƯỢC DÙNG. Cụ thể:
      • thùng MỚI tạo từ phiếu: chưa có allocation nào (chưa xuất đơn/hủy/chuyển);
      • thùng CÓ SẴN đã cộng thêm: remaining hiện tại ≥ số đã cộng (phần cộng thêm
        chưa bị tiêu vào đâu) — gỡ allocation purchase_in xong remaining không âm.
    Vi phạm 1 dòng → trả lỗi, KHÔNG hoàn dòng nào. Thùng đã bị admin xoá hẳn → bỏ qua.
    Xong: GIỮ NGUYÊN thùng mới (để user xóa từng thùng hoặc nhập bổ sung), gỡ
    allocation purchase_in ở thùng có sẵn, clear goods_handled_* và giữ snapshot
    các thùng mới → phiếu mở khoá. Trả (info, None) hoặc (None, lỗi VN)."""
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
        retained_boxes: list[int] = []     # thùng mới giữ nguyên
        to_unalloc: list[int] = []         # allocation purchase_in sẽ gỡ
        for e in new_entries:
            box = get_box(conn, e.get("box_id"))
            if not box:
                continue                    # admin đã xoá thùng → coi như xử lý rồi
            allocs = list_box_allocations(conn, box["id"])
            if allocs:
                return None, (f"Thùng {box.get('box_code')} ({e.get('sp')}) đã phát sinh "
                              f"{len(allocs)} bút toán nhập/xuất/chuyển — không hủy chốt được")
            retained_boxes.append(box["id"])
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
        # Giữ goods_result của các thùng mới làm trạng thái nền cho lần chốt tiếp
        # theo; phần nhập vào thùng có sẵn đã hoàn nên loại khỏi snapshot.
        retained_result = {
            "restocked_new": [e for e in new_entries if e.get("box_id") in retained_boxes],
            "restocked_existing": [],
        }
        conn.execute(
            "UPDATE purchase_slips SET goods_handled_at = NULL, goods_handled_by = NULL, goods_result = ?"
            " WHERE id = ?", (_json.dumps(retained_result, ensure_ascii=False), purchase_id))
    return {"retained_boxes": retained_boxes, "removed_allocations": len(to_unalloc),
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
