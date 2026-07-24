"""Xử lý HÀNG khách trả về — orchestration thuần (nhập kho / tạo thùng / xuất hủy).

Không HTTP/realtime — chỉ thao tác store trong 1 connection để route gọi + unit-test
(tests/test_return_goods.py). Trả kèm extra['audit'] (snapshot thùng sau biến động,
server_app.inventory_audit.box_snapshot) để ROUTE ghi event kho box.created/box.return_in
→ timeline thùng/SP/vị trí thấy hàng trả về. Nối: inventory_store.queries
(add_boxes/get_box/update_box), disposal_store (box-less create_manual_disposal),
return_store (mark_goods_handled).

Ba cách xử lý mỗi dòng hàng trả:
  • restock_existing — nhập vào 1 thùng CÓ SẴN: allocation ÂM return_in, remaining tăng, quantity gốc giữ nguyên.
  • restock_new      — TẠO thùng mới cho hàng trả (chọn vị trí/đơn vị).
  • dispose          — gom vào 1 phiếu XUẤT HỦY box-less (chỉ ghi nhận, KHÔNG trừ tồn).

KIỂM TRƯỚC — GHI SAU (khớp purchase_goods): pass 1 validate TOÀN BỘ dòng, dòng
hỏng trả lỗi VN nêu rõ dòng nào, CHƯA claim phiếu (goods_handled_at giữ NULL →
sửa xong gọi lại được). Chỉ khi mọi dòng hợp lệ mới CAS claim + ghi kho, tất cả
trong 1 transaction — lỗi giữa chừng raise → rollback CẢ claim.
"""
from __future__ import annotations

import json as _json
from datetime import datetime as _dt, timezone as _tz, timedelta as _td

from utils.qty import parse_qty


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — khớp return_store claim_goods_handling
    return _dt.now(_tz(_td(hours=7))).isoformat(timespec="seconds")


class _ApplyError(Exception):
    """Lỗi ghi kho giữa chừng — raise để transaction rollback cả lô (kể cả claim)."""


def _validate_dispositions(conn, r: dict, dispositions) -> tuple[list[dict], str | None]:
    """Pass 1: chuẩn hoá + kiểm MỌI dòng trước khi ghi — lỗi trả rõ dòng nào,
    KHÔNG bỏ qua lặng (dòng lặng = hàng biến mất không dấu vết, phiếu lại bị khoá).
    Trần theo phiếu trả: mỗi SP xử lý (nhập thùng / tạo thùng / hủy) không vượt
    tổng sl của SP đó trên phiếu — key = danh tính SP (products.id, fallback mã)
    để mã đổi tên giữa chừng vẫn khớp. Trả (valid_rows, None) | ([], lỗi VN)."""
    from inventory_store.queries import get_box
    from server_app.purchase_goods import _product_key

    limits: dict = {}
    labels: dict = {}
    for it in (r.get("items") or []):
        code_i = str((it or {}).get("sp") or "").strip().upper()
        sl = parse_qty((it or {}).get("sl"))
        if not code_i or sl <= 0:
            continue
        key_i, live_i = _product_key(conn, code_i, (it or {}).get("sp_id"))
        limits[key_i] = limits.get(key_i, 0.0) + sl
        labels[key_i] = live_i or code_i

    used: dict = {}
    valid: list[dict] = []
    for disp in dispositions or []:
        if not isinstance(disp, dict):
            return [], "Dòng xử lý hàng trả không hợp lệ"
        action = str(disp.get("action") or "").strip()
        if action in ("", "skip"):
            continue
        if action not in ("restock_existing", "restock_new", "dispose"):
            return [], "Cách xử lý hàng trả không hợp lệ"
        code = str(disp.get("sp") or "").strip().upper()
        if not code:
            return [], "Thiếu mã sản phẩm ở dòng xử lý hàng trả"
        q = parse_qty(disp.get("quantity"))   # NaN/Infinity/lỗi → 0.0 → chặn ngay dưới
        if q <= 0:
            return [], f"Số lượng xử lý của {code} phải > 0"
        key, live_code = _product_key(conn, code)
        if key not in limits:
            return [], f"Mã {live_code or code} không có trên phiếu trả"
        row = {"action": action, "sp": code, "quantity": q, "key": key}
        if action == "restock_existing":
            try:
                box_id = int(disp.get("box_id"))
            except (TypeError, ValueError):
                return [], f"Chọn thùng hợp lệ để nhập {live_code or code}"
            box = get_box(conn, box_id)
            if not box:
                return [], f"Không tìm thấy thùng để nhập {live_code or code}"
            if box.get("disabled"):
                return [], (f"Thùng {box.get('box_code')} đã vô hiệu — kích hoạt lại "
                            f"rồi xử lý hàng trả")
            # Thùng phải CÙNG SP với dòng hàng trả — nhận nhầm là sai tồn cả 2 mã.
            box_key, box_code = _product_key(conn, box.get("product_code"), box.get("product_id"))
            if box_key != key:
                return [], f"Thùng {box.get('box_code')} là mã {box_code}, không phải {live_code or code}"
            row.update({"box_id": box_id, "box_code": box.get("box_code")})
        elif action == "restock_new":
            row.update({"place_id": disp.get("place_id"), "unit_id": disp.get("unit_id")})
        if used.get(key, 0.0) + q > limits[key] + 1e-9:
            return [], (f"Mã {labels.get(key) or live_code or code} xử lý vượt số trên phiếu trả "
                        f"({used.get(key, 0.0) + q:g} > {limits[key]:g})")
        used[key] = used.get(key, 0.0) + q
        valid.append(row)
    return valid, None


def apply_goods_dispositions(conn, return_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Áp dụng từng disposition cho hàng trả của phiếu return_id.

    dispositions = [{sp, quantity, action, box_id?, place_id?, unit_id?}].
    Trả (extra, None) với extra = {result, touched_boxes, disposal, customer_key},
    hoặc (None, 'not_found'|'already'|lỗi VN). KIỂM TRƯỚC toàn bộ (pass 1) —
    dòng hỏng (thiếu mã / số ≤ 0 / thùng mất / thùng vô hiệu / khác SP / SP không
    có trên phiếu / vượt trần) → trả lỗi, phiếu CHƯA bị claim, sửa xong gọi lại
    được. Hợp lệ hết mới CAS claim + ghi, cùng 1 transaction (all-or-nothing)."""
    from inventory_store.queries import add_boxes
    from inventory_store.allocations import receive_return_stock
    from disposal_store import create_manual_disposal
    from return_store import get_return, ensure_returns_schema
    from utils.db import transaction

    ensure_returns_schema(conn)   # DDL trước khi mở transaction
    # add_boxes/receive_return_stock/create_manual_disposal dùng `with transaction`
    # re-entrant (an toàn). claim_goods_handling/set_goods_result commit trần → INLINE SQL.
    try:
        with transaction(conn):
            r = get_return(conn, return_id)
            if not r:
                return None, "not_found"
            if r.get("goods_handled_at"):
                return None, "already"

            # ── PASS 1: validate TOÀN BỘ — lỗi trả ra khi phiếu CHƯA claim ──
            valid, verr = _validate_dispositions(conn, r, dispositions)
            if verr:
                return None, verr

            # ── PASS 2: giành quyền NGUYÊN TỬ (CAS) rồi mới ghi — 2 request đồng
            # thời không double-apply; lỗi ghi giữa chừng raise → rollback cả CAS.
            claimed = conn.execute(
                "UPDATE return_slips SET goods_handled_at = ?, goods_handled_by = ? "
                "WHERE id = ? AND goods_handled_at IS NULL",
                (_now_vn(), actor or "", return_id))
            if claimed.rowcount != 1:
                return None, "already"

            result: dict = {"restocked_existing": [], "restocked_new": [], "disposed": [], "disposal_id": None}
            touched_boxes: list[int] = []
            dispose_items: list[dict] = []
            created_ids: list[int] = []                    # thùng MỚI tạo (audit kho)
            return_in: list[tuple[int, float]] = []        # (box_id, q cộng vào) (audit kho)
            for disp in valid:
                action, code, q = disp["action"], disp["sp"], disp["quantity"]
                if action == "restock_existing":
                    box_id = disp["box_id"]
                    # Ghi allocation ÂM 'return_in' — remaining tăng q, quantity gốc GIỮ NGUYÊN
                    # (không thổi phồng boxed_total phiếu SX nguồn). Xem receive_return_stock.
                    if not receive_return_stock(conn, box_id, q, return_id, by=actor):
                        raise _ApplyError(f"Không nhập được hàng vào thùng {disp.get('box_code')}")
                    touched_boxes.append(box_id)
                    return_in.append((box_id, q))
                    result["restocked_existing"].append(
                        {"sp": code, "quantity": q, "box_id": box_id, "box_code": disp.get("box_code")})
                elif action == "restock_new":
                    # SP NGUYÊN KIỆN (vai 📦): 1 kiện = 1 dòng thùng — modal trả hàng không
                    # có ô "số thùng" nên server TỰ TÁCH: 75 (kiện 30) → 2 kiện dán nhãn
                    # đơn vị + 1 thùng lẻ 15 (đường thường). SP không vai → 1 thùng như cũ.
                    from product_store.units import bulk_role_by_code
                    bulk = bulk_role_by_code(conn, code)
                    f = float(bulk["factor"]) if (bulk and bulk.get("factor")) else 0.0
                    if f > 0 and q > f + 1e-9:
                        n_kien = int((q + 1e-9) // f)
                        le = round(q - n_kien * f, 6)
                        parts = [(f, bulk["name"])] * n_kien + ([(le, None)] if le > 1e-9 else [])
                    elif f > 0 and abs(q - f) < 1e-9:
                        parts = [(q, bulk["name"])]
                    else:
                        parts = [(q, None)]
                    for pq, plabel in parts:
                        try:
                            boxes = add_boxes(conn, code, [pq], place_id=disp.get("place_id"),
                                              unit_id=None if plabel else disp.get("unit_id"),
                                              unit_label=plabel, by=actor,
                                              source_return_id=return_id,
                                              note=f"Hàng khách trả (phiếu trả #{return_id})")
                        except ValueError as exc:   # hết số gọi… → rollback cả lô
                            raise _ApplyError(f"Không tạo được thùng cho {code}: {exc}")
                        if not boxes:
                            raise _ApplyError(f"Không tạo được thùng cho {code}")
                        touched_boxes.append(boxes[0]["id"])
                        created_ids.append(boxes[0]["id"])
                        result["restocked_new"].append(
                            {"sp": code, "quantity": pq, "box_id": boxes[0]["id"], "box_code": boxes[0]["box_code"]})
                elif action == "dispose":
                    dispose_items.append({"product_code": code, "quantity": q})

            disposal = None
            if dispose_items:
                disposal, derr = create_manual_disposal(
                    conn, dispose_items, reason=f"Hàng khách trả — huỷ (phiếu trả #{return_id})",
                    by=actor, source_return_id=return_id)
                if not disposal:
                    raise _ApplyError(str(derr or "Không tạo được phiếu xuất hủy"))
                result["disposed"] = disposal["items"]
                result["disposal_id"] = disposal["id"]

            # inline set_goods_result(conn, return_id, result) — tránh bare commit
            conn.execute("UPDATE return_slips SET goods_result = ? WHERE id = ?",
                         (_json.dumps(result, ensure_ascii=False), return_id))
    except _ApplyError as exc:
        return None, str(exc)
    # Snapshot thùng SAU biến động (đã commit) → route ghi event kho scope box
    # (box.created / box.return_in — timeline thùng/SP/vị trí đọc).
    from server_app.inventory_audit import box_snapshot
    audit = {"created": [s for bid in created_ids if (s := box_snapshot(conn, bid))],
             "return_in": [dict(s, taken=q) for bid, q in return_in
                           if (s := box_snapshot(conn, bid))]}
    return {"result": result, "touched_boxes": touched_boxes, "audit": audit,
            "disposal": disposal, "customer_key": r.get("customer_key")}, None
