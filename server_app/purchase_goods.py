"""Nhập KHO hàng mua về từ phiếu NHẬP HÀNG — flow GIỐNG XUẤT KHO ĐƠN HÀNG.

Phiếu MỞ: ghi nhập TỪNG DÒNG thoải mái (receive_purchase_lines — tạo N thùng mới
giống nhau như phiếu SX / cộng vào thùng có sẵn bằng allocation ÂM 'purchase_in'),
gỡ từng dòng (unreceive_purchase_line) hoặc xoá từng thùng; nhập ĐỦ mọi mã theo
phiếu mới CHỐT được (confirm_purchase_receipt — CAS goods_handled_at + snapshot
goods_result → khoá phiếu; thiếu → lỗi, sửa SL phiếu về số thực nhận nếu hàng về
thiếu/vỡ). Trạng thái ĐANG NHẬP derive LIVE từ kho (_draft_receipt: thùng
source_purchase_id + allocation purchase_in) — không có bảng state riêng.
Hủy chốt (undo) mở khoá, GIỮ thùng → quay về trạng thái đang nhập. Server luôn
chặn nhập vượt số/mã trên phiếu (cộng dồn theo SP).

Không HTTP/realtime — chỉ thao tác store trong 1 connection để route gọi +
unit-test (tests/test_purchase_goods.py). Mỗi hàm ghi/gỡ kho trả kèm
extra['audit'] (snapshot thùng sau biến động) để ROUTE ghi event kho scope box
(box.created / box.purchase_in / box.purchase_in_removed — timeline thùng/SP/vị trí
đọc). Phần đọc cho API (attach boxes/draft): server_app/purchase_goods_view.py.
Nối: inventory_store.queries/allocations, purchase_store, product_store.
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


def _audit_snap(conn, box_id, taken=None) -> dict | None:
    """Ảnh chụp thùng SAU biến động cho audit kho (khớp shape inventory_audit.box_snapshot
    — không import server_app để module này vẫn store-thuần, unit-test không kéo aiohttp)."""
    from inventory_store.queries import get_box
    box = get_box(conn, box_id)
    if not box:
        return None
    snap = {"box_id": box["id"], "place_id": box.get("place_id"), "place_name": box.get("place_name"),
            "box_code": box.get("box_code"), "product_code": box.get("product_code"),
            "unit": box.get("product_unit") or "cây",
            "quantity": box.get("quantity"), "remaining": _box_remaining(conn, box_id, box)}
    if taken is not None:
        snap["taken"] = taken
    return snap


def _audit_snaps(conn, entries: list[tuple[int, float | None]]) -> list[dict]:
    return [s for bid, taken in entries if (s := _audit_snap(conn, bid, taken))]


def _draft_receipt(conn, purchase_id: int) -> dict:
    """Trạng thái ĐANG NHẬP của phiếu — derive live từ kho, không bảng riêng:
    new = thùng còn sống tạo từ phiếu (source_purchase_id, quantity > 0);
    existing = từng allocation 'purchase_in' của phiếu (cộng vào thùng có sẵn);
    used = tổng đã nhập theo SP (key _product_key) để so trần trên phiếu."""
    out = {"new": [], "existing": [], "used": {}}
    if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_boxes'").fetchone():
        return out   # DB chưa bật tính năng kho
    for raw in conn.execute(
            "SELECT * FROM inventory_boxes WHERE source_purchase_id = ? ORDER BY id",
            (int(purchase_id),)).fetchall():
        box = dict(raw)
        q = float(box.get("quantity") or 0)
        if q <= 0:
            continue
        key, code = _product_key(conn, box.get("product_code"), box.get("product_id"))
        out["used"][key] = out["used"].get(key, 0.0) + q
        # sp_id để client khớp dòng phiếu theo danh tính SP (mã đổi tên vẫn khớp)
        out["new"].append({"sp": code, "sp_id": key[1] if key[0] == "id" else None,
                           "quantity": q, "box_id": box["id"],
                           "box_code": box.get("box_code")})
    for r in conn.execute(
            "SELECT a.id AS allocation_id, a.box_id, a.quantity, b.box_code,"
            " b.product_code, b.product_id"
            " FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id"
            " WHERE a.kind = 'purchase_in' AND a.order_thread_id = ? ORDER BY a.id",
            (int(purchase_id),)).fetchall():
        q = -float(r["quantity"] or 0)   # dòng purchase_in quantity ÂM
        if q <= 0:
            continue
        key, code = _product_key(conn, r["product_code"], r["product_id"])
        out["used"][key] = out["used"].get(key, 0.0) + q
        out["existing"].append({"sp": code, "sp_id": key[1] if key[0] == "id" else None,
                                "quantity": q, "box_id": r["box_id"],
                                "box_code": r["box_code"], "allocation_id": r["allocation_id"]})
    return out


def _validate_purchase_dispositions(conn, purchase: dict, dispositions, *,
                                    initial_used: dict[tuple[str, int | str], float] | None = None
                                    ) -> tuple[list[dict], str | None]:
    """Chuẩn hoá và kiểm disposition trước khi ghi, lỗi trả rõ — không bỏ qua lặng."""
    limits, labels = _purchase_item_limits(conn, purchase.get("items") or [])
    used: dict[tuple[str, int | str], float] = dict(initial_used or {})
    for key, qty in used.items():
        if key not in limits or qty > limits[key] + 1e-9:
            return [], (f"Phần đã nhập của mã {labels.get(key) or key[1]} vượt số trên phiếu "
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
            # NGUYÊN KIỆN (vai 📦, server tự resolve — không tin client): 1 thùng = tối
            # đa 1 kiện; đúng kiện (q == factor) → nhãn chứa = TÊN ĐƠN VỊ, khỏi chọn
            # đơn vị chứa; lẻ (< kiện — hàng xá/vỡ) → đường cũ unit_id; vượt kiện → chặn.
            from product_store.units import bulk_role_by_code, bulk_label_for_qty
            bulk = bulk_role_by_code(conn, live_code or code)
            label, berr = bulk_label_for_qty(bulk, q)
            if berr:
                return [], f"{live_code or code}: {berr}"
            if label:
                row.update({"count": count, "place_id": place_id, "unit_id": None,
                            "unit_label": label})
            else:
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


def _apply_lines(conn, purchase_id: int, valid: list[dict], actor: str
                 ) -> tuple[list[int], list[int], list[tuple[int, float]]]:
    """Ghi các dòng ĐÃ validate vào kho (trong transaction của caller).
    Lỗi giữa chừng raise _ReceiptApplyError → caller rollback cả lô.
    Trả (touched, created_ids, added) — created_ids = thùng MỚI tạo,
    added = [(box_id, q)] các lần cộng vào thùng có sẵn (cho audit kho)."""
    from inventory_store.queries import add_boxes
    from inventory_store.allocations import receive_purchase_stock
    touched: list[int] = []
    created: list[int] = []
    added: list[tuple[int, float]] = []
    for disp in valid:
        code = disp["sp"]
        q = float(disp["quantity"])
        if disp["action"] == "restock_existing":
            box_id = int(disp["box_id"])
            if not receive_purchase_stock(conn, box_id, q, purchase_id, by=actor):
                raise _ReceiptApplyError(f"Không nhập được hàng vào thùng {disp.get('box_code')}")
            touched.append(box_id)
            added.append((box_id, q))
        elif disp["action"] == "restock_new":
            # count = số thùng giống nhau (như nhập thùng phiếu SX); mỗi thùng q hàng.
            count = int(disp.get("count") or 1)
            try:
                boxes = add_boxes(conn, code, [q] * count, source_purchase_id=purchase_id,
                                  place_id=disp.get("place_id"), unit_id=disp.get("unit_id"),
                                  unit_label=disp.get("unit_label"),
                                  by=actor, note=f"Nhập hàng NCC (phiếu nhập #{purchase_id})")
            except ValueError:
                raise _ReceiptApplyError("Không còn số gọi trống để tạo thùng mới")
            touched += [bx["id"] for bx in boxes]
            created += [bx["id"] for bx in boxes]
    return touched, created, added


def _missing_items(conn, purchase: dict, used: dict) -> list[dict]:
    """Các mã CHƯA nhập đủ so với phiếu. Rule: chưa đủ thì KHÔNG cho chốt —
    hàng về thiếu/vỡ phải sửa SL trên phiếu về số thực nhận rồi mới chốt."""
    limits, labels = _purchase_item_limits(conn, purchase.get("items") or [])
    return [{"sp": labels.get(k) or k[1], "missing": round(lim - used.get(k, 0.0), 3)}
            for k, lim in limits.items() if used.get(k, 0.0) + 1e-6 < lim]


def _missing_error(missing: list[dict]) -> str:
    detail = ", ".join(f"{m['sp']} thiếu {m['missing']:g}" for m in missing)
    return (f"Chưa nhập đủ hàng vào kho — {detail}. Nhập thêm cho đủ; "
            "hàng về thiếu/vỡ thì sửa SL trên phiếu về số thực nhận rồi chốt.")


def _snapshot(draft: dict) -> dict:
    """goods_result từ trạng thái đang nhập — 1 entry / thùng mới, 1 entry / lần cộng."""
    keep = ("sp", "quantity", "box_id", "box_code")
    return {"restocked_new": [{k: e[k] for k in keep} for e in draft["new"]],
            "restocked_existing": [{k: e[k] for k in keep} for e in draft["existing"]]}


def receive_purchase_lines(conn, purchase_id: int, dispositions, *, actor: str = "") -> tuple[dict | None, str | None]:
    """Ghi nhập kho TỪNG ĐỢT khi phiếu ĐANG MỞ (như xuất kho từng thùng cho đơn).
    Không chốt, gọi được nhiều lần; trần = số trên phiếu trừ phần ĐÃ nhập."""
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    try:
        with transaction(conn):
            p = get_purchase(conn, purchase_id)
            if not p or p.get("deleted_at"):
                return None, "not_found"
            if p.get("goods_handled_at"):
                return None, "Phiếu đã chốt nhập kho — hủy chốt trước khi nhập thêm"
            draft = _draft_receipt(conn, purchase_id)
            valid, err = _validate_purchase_dispositions(
                conn, p, dispositions, initial_used=draft["used"])
            if err:
                return None, err
            if not valid:
                return None, "Chưa có dòng nào để nhập kho"
            touched, created, added = _apply_lines(conn, purchase_id, valid, actor)
    except _ReceiptApplyError as exc:
        return None, str(exc)
    audit = {"created": _audit_snaps(conn, [(b, None) for b in created]),
             "purchase_in": _audit_snaps(conn, added)}
    return {"touched_boxes": touched, "supplier_id": p.get("supplier_id"),
            "audit": audit}, None


def confirm_purchase_receipt(conn, purchase_id: int, *, actor: str = "") -> tuple[dict | None, str | None]:
    """CHỐT nhập kho (như 'chốt xuất kho' của đơn): CAS goods_handled_at, chụp
    trạng thái đang nhập vào goods_result → phiếu khoá sửa/xoá. CHỈ chốt khi đã
    nhập ĐỦ mọi mã theo phiếu (như chốt xuất kho đòi xuất đủ) — thiếu trả lỗi;
    hàng về thiếu/vỡ thì sửa SL trên phiếu về số thực nhận rồi chốt."""
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    with transaction(conn):
        p = get_purchase(conn, purchase_id)
        if not p or p.get("deleted_at"):
            return None, "not_found"
        draft = _draft_receipt(conn, purchase_id)
        limits, labels = _purchase_item_limits(conn, p.get("items") or [])
        for key, lim in limits.items():
            got = draft["used"].get(key, 0.0)
            if got > lim + 1e-9:   # phòng hờ — receive đã chặn, items đã guard
                return None, (f"Phần đã nhập của mã {labels.get(key) or key[1]} vượt số trên phiếu "
                              f"({got:g} > {lim:g}) — gỡ bớt trước khi chốt")
        missing = _missing_items(conn, p, draft["used"])
        if missing:
            return None, _missing_error(missing)
        claimed = conn.execute(
            "UPDATE purchase_slips SET goods_handled_at = ?, goods_handled_by = ? "
            "WHERE id = ? AND goods_handled_at IS NULL",
            (_now_vn(), actor or "", purchase_id))
        if claimed.rowcount != 1:
            return None, "already"
        result = _snapshot(draft)
        conn.execute("UPDATE purchase_slips SET goods_result = ? WHERE id = ?",
                     (_json.dumps(result, ensure_ascii=False), purchase_id))
    touched = [e["box_id"] for e in draft["new"] + draft["existing"]]
    return {"result": result, "touched_boxes": touched, "missing": [],
            "supplier_id": p.get("supplier_id")}, None


def unreceive_purchase_line(conn, purchase_id: int, allocation_id) -> tuple[dict | None, str | None]:
    """Gỡ 1 dòng 'cộng vào thùng có sẵn' khi phiếu ĐANG MỞ (như thu hồi 1 thùng
    khỏi đơn). Guard: phần đã cộng chưa bị tiêu — gỡ xong remaining không âm."""
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
    with transaction(conn):
        p = get_purchase(conn, purchase_id)
        if not p or p.get("deleted_at"):
            return None, "Không tìm thấy phiếu nhập"
        if p.get("goods_handled_at"):
            return None, "Phiếu đã chốt nhập kho — hủy chốt trước khi gỡ"
        try:
            aid = int(allocation_id)
        except (TypeError, ValueError):
            return None, "Dòng nhập kho không hợp lệ"
        row = conn.execute(
            "SELECT a.*, b.box_code, b.quantity AS box_quantity FROM box_allocations a"
            " JOIN inventory_boxes b ON b.id = a.box_id WHERE a.id = ?", (aid,)).fetchone()
        if (not row or (row["kind"] or "") != "purchase_in"
                or int(row["order_thread_id"] or 0) != int(purchase_id)):
            return None, "Không tìm thấy dòng nhập kho để gỡ"
        q_in = -float(row["quantity"] or 0)
        used = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?",
            (row["box_id"],)).fetchone()[0]
        remaining = float(row["box_quantity"] or 0) - float(used or 0)
        if remaining < q_in - 1e-9:
            return None, (f"Thùng {row['box_code']} đã dùng một phần hàng nhập "
                          f"(còn {remaining:g} < {q_in:g} đã cộng) — không gỡ được")
        conn.execute("DELETE FROM box_allocations WHERE id = ?", (aid,))
    return {"box_id": row["box_id"], "box_code": row["box_code"], "quantity": q_in,
            "supplier_id": p.get("supplier_id"),
            "audit": {"purchase_in_removed": _audit_snaps(conn, [(row["box_id"], q_in)])}}, None


def undo_purchase_receipt(conn, purchase_id: int) -> tuple[dict | None, str | None]:
    """HỦY CHỐT nhập kho (admin) — mở khóa, GIỮ NGUYÊN thùng mới → phiếu quay về
    trạng thái ĐANG NHẬP (xoá từng thùng / nhập bổ sung / chốt lại được).

    Điều kiện: hàng nhập CHƯA ĐƯỢC DÙNG. Cụ thể:
      • thùng MỚI tạo từ phiếu: chưa có allocation nào (chưa xuất đơn/hủy/chuyển);
      • thùng CÓ SẴN đã cộng thêm: remaining hiện tại ≥ số đã cộng — gỡ allocation
        purchase_in xong remaining không âm.
    Vi phạm 1 dòng → trả lỗi, KHÔNG hoàn dòng nào. Thùng đã xoá hẳn → bỏ qua.
    Xong: gỡ allocation purchase_in, clear goods_handled_* + goods_result (trạng
    thái đang nhập derive live từ kho, không cần snapshot)."""
    from inventory_store.queries import get_box
    from inventory_store.allocations import list_box_allocations
    from purchase_store import get_purchase, ensure_purchases_schema
    from utils.db import transaction

    ensure_purchases_schema(conn)   # DDL trước khi mở transaction
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
        removed_per_box: list[tuple[int, float]] = []   # (box_id, tổng gỡ) cho audit kho
        for e in new_entries:
            box = get_box(conn, e.get("box_id"))
            if not box:
                continue                    # admin đã xoá thùng → coi như xử lý rồi
            allocs = list_box_allocations(conn, box["id"])
            if allocs:
                return None, (f"Thùng {box.get('box_code')} ({e.get('sp')}) đã phát sinh "
                              f"{len(allocs)} bút toán nhập/xuất/chuyển — không hủy chốt được")
            retained_boxes.append(box["id"])
        seen_boxes: set[int] = set()
        for e in exist_entries:
            bid = e.get("box_id")
            if bid in seen_boxes:
                continue
            seen_boxes.add(bid)
            box = get_box(conn, bid)
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
            if q_in > 0:
                removed_per_box.append((box["id"], q_in))
        # ── Áp dụng ──
        for aid in to_unalloc:
            conn.execute("DELETE FROM box_allocations WHERE id = ?", (aid,))
        conn.execute(
            "UPDATE purchase_slips SET goods_handled_at = NULL, goods_handled_by = NULL, goods_result = NULL"
            " WHERE id = ?", (purchase_id,))
    return {"retained_boxes": retained_boxes, "removed_allocations": len(to_unalloc),
            "supplier_id": p.get("supplier_id"),
            "audit": {"purchase_in_removed": _audit_snaps(conn, removed_per_box)}}, None
