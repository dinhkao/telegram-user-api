"""Format CHI TIẾT từng domain-event audit → (nhãn VN, parts có link).

Bảng tra duy nhất cho MỌI event nghiệp vụ (order.* / box.* / return.* / quy.* /
disposal.* / product.* / stocktake.* / settings.*...) — 3 mặt lịch sử (đơn,
thực thể, toàn cục #/lich-su) đều gọi qua đây để không lệch nhãn. Payload event
cũ thiếu field → Resolver tra DB bù (best-effort). Nối: server_app/history_format,
order_history, entity_history, activity.
"""
from __future__ import annotations

from server_app.history_format import (
    Resolver, box_part, boxnum, customer_part, href_for, money, part,
    product_href, qty,
)

_SETTING_VI = {"soan_hang_require_stock": "Soạn hàng phải chốt xuất kho + có ảnh"}


def _sp(code, resolver: Resolver | None) -> dict:
    """Part mã SP (kèm tên nếu tra được) → link trang SP."""
    name = resolver.product_name(code) if resolver else None
    return part(f"{code}{' – ' + name if name else ''}", product_href(code))


def _join(parts_groups: list[list[dict]], sep: str = " · ") -> list[dict]:
    out: list[dict] = []
    for g in parts_groups:
        if not g:
            continue
        if out:
            out.append(part(sep))
        out.extend(g)
    return out


def stock_boxes_parts(boxes: list[dict], verb: str, resolver: Resolver | None) -> list[dict]:
    """boxes=[{box_id,box_code,product_code,taken,remaining?,unit?}] → parts chi
    tiết từng thùng: 'lấy 5 cây KDX D30 từ thùng 322 (còn 15)'."""
    groups = []
    for b in boxes or []:
        info = resolver.box_brief(b.get("box_id")) if resolver else None
        pc = b.get("product_code") or (info or {}).get("product_code") or ""
        unit = b.get("unit") or (info or {}).get("unit") or "cây"
        seg = [part(f"{verb} {qty(b.get('taken'))} {unit} ")]
        if pc:
            seg.append(_sp(pc, resolver))
            seg.append(part(" "))
        seg.append(part("từ " if verb == "lấy" else "về "))
        seg.append(box_part(b.get("box_id"), b.get("box_code"), resolver))
        if b.get("remaining") is not None:
            seg.append(part(f" (thùng còn {qty(b.get('remaining'))})"))
        groups.append(seg)
    return _join(groups, sep="; ")


def _inv_box_parts(p: dict, resolver, *, with_box: bool = True) -> list[dict]:
    """Đầu dòng biến động kho: [SP link] · [thùng link]."""
    seg = []
    if p.get("product_code"):
        seg.append([_sp(p.get("product_code"), resolver)])
    if with_box:
        seg.append([box_part(p.get("box_id"), p.get("box_code"), resolver)])
    return _join(seg)


def _order_ref(p: dict, resolver) -> list[dict]:
    tid = p.get("order_thread_id")
    if not tid:
        return []
    txt = p.get("order_text") or (resolver.order_text(tid) if resolver else None) or f"#{tid}"
    txt = str(txt)[:40]
    box = f"?focus=box:{p.get('box_id')}" if p.get("box_id") else ""
    return [part("đơn "), part(f"“{txt}”", f"#/order/{tid}{box}")]


def event_entry(action: str, p: dict, resolver: Resolver | None) -> tuple[str, list[dict]] | None:
    """1 domain event → (label, parts). None = không biết action này.
    KHÔNG BAO GIỜ raise — 1 payload hỏng không được giết cả trang lịch sử/feed
    (bài học disposal.deleted 2026-07-14: len(int) → feed trắng từ trang 9)."""
    try:
        return _event_entry(action, p, resolver)
    except Exception:
        import logging
        logging.getLogger("event_format").warning("event_entry(%s) lỗi payload=%r", action, p, exc_info=True)
        return None


def _event_entry(action: str, p: dict, resolver: Resolver | None) -> tuple[str, list[dict]] | None:
    p = p if isinstance(p, dict) else {}

    # ── ĐƠN ────────────────────────────────────────────────────────────────
    if action == "order.created":
        return "Tạo đơn", []
    if action == "order.changed":
        return "Cập nhật đơn (Telegram)", []
    if action == "order.image_added":
        src = {"kiotviet_invoice": "ảnh hoá đơn KiotViet", "payment_receipt": "ảnh phiếu thu"}.get(p.get("source"))
        return "Thêm ảnh", [part(src)] if src else []
    if action == "order.image_deleted":
        return "Xóa ảnh", [part(str(p.get("reason") or ""))] if p.get("reason") else []
    if action in ("order.stock_allocated", "order.stock_released"):
        verb = "lấy" if action == "order.stock_allocated" else "trả"
        label = "Xuất kho cho đơn" if action == "order.stock_allocated" else "Thu hồi hàng về kho"
        return label, stock_boxes_parts(p.get("boxes") or [], verb, resolver)
    if action == "order.stock_confirmed":
        return "Chốt xuất kho", [part("khoá sửa phân bổ, đơn sẵn sàng soạn")]
    if action == "order.stock_unconfirmed":
        return "Bỏ chốt xuất kho", []
    if action == "order.bulk_payment":
        seg = [part(money(p.get("amount")))]
        m = {"cash": "tiền mặt", "transfer": "chuyển khoản", "Transfer": "chuyển khoản"}.get(str(p.get("method") or ""))
        if m:
            seg.append(part(f" · {m}"))
        if p.get("source_thread_id"):
            seg.append(part(" · thu tại "))
            seg.extend(_order_ref({"order_thread_id": p.get("source_thread_id")}, resolver))
        return "Thu tiền gộp", seg

    # ── KHO (thùng / vị trí) ───────────────────────────────────────────────
    if action == "box.created":
        src = []
        if p.get("purchase_id"):
            src = [part(f"phiếu nhập #{p['purchase_id']} →", href_for("purchase", p.get("purchase_id")))]
        elif p.get("return_id"):
            src = [part(f"hàng khách trả (phiếu trả #{p['return_id']}) →", href_for("return", p.get("return_id")))]
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"nhập {qty(p.get('quantity'))}")] if p.get("quantity") is not None else [],
                     src])
        return "Nhập thùng vào kho", seg
    if action in ("box.purchase_in", "box.purchase_in_removed"):
        verb = "cộng" if action == "box.purchase_in" else "gỡ"
        label = "Nhập hàng NCC vào thùng" if action == "box.purchase_in" else "Gỡ hàng nhập khỏi thùng"
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"{verb} {qty(p.get('taken'))}")] if p.get("taken") is not None else [],
                     [part(f"phiếu nhập #{p.get('purchase_id')} →", href_for("purchase", p.get("purchase_id")))] if p.get("purchase_id") else [],
                     [part(f"thùng còn {qty(p.get('remaining'))}")] if p.get("remaining") is not None else []])
        return label, seg
    if action == "box.return_in":
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"cộng {qty(p.get('taken'))}")] if p.get("taken") is not None else [],
                     [part(f"phiếu trả #{p.get('return_id')} →", href_for("return", p.get("return_id")))] if p.get("return_id") else [],
                     [part(f"thùng còn {qty(p.get('remaining'))}")] if p.get("remaining") is not None else []])
        return "Khách trả hàng vào thùng", seg
    if action in ("box.allocated", "box.released"):
        verb = "lấy" if action == "box.allocated" else "trả"
        label = "Xuất cho đơn" if action == "box.allocated" else "Thu hồi về kho"
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"{verb} {qty(p.get('taken'))}")] if p.get("taken") is not None else [],
                     _order_ref(p, resolver),
                     [part(f"thùng còn {qty(p.get('remaining'))}")] if p.get("remaining") is not None else []])
        return label, seg
    if action == "box.moved":
        seg = _join([_inv_box_parts(p, resolver),
                     [part("từ "), part(p.get("from_name") or "Chưa xếp", href_for("place", p.get("from_place_id"))),
                      part(" → "), part(p.get("to_name") or "Chưa xếp", href_for("place", p.get("to_place_id")))]])
        return "Chuyển kho", seg
    if action == "box.moved_out":
        return "Thùng chuyển đi", _join([_inv_box_parts(p, resolver),
                                         [part("→ "), part(p.get("to_name") or "Chưa xếp", href_for("place", p.get("to_place_id")))]])
    if action == "box.moved_in":
        return "Thùng chuyển đến", _join([_inv_box_parts(p, resolver),
                                          [part("từ "), part(p.get("from_name") or "Chưa xếp", href_for("place", p.get("from_place_id")))]])
    if action == "box.consumed":
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"tiêu hao {qty(p.get('taken'))}")] if p.get("taken") is not None else [],
                     [part("đóng gói "), _sp(p.get("target_code"), resolver)] if p.get("target_code") else [],
                     [part("phiếu SX →", href_for("production", p.get("slip_id")))] if p.get("slip_id") else []])
        return "Tiêu hao đóng gói", seg
    if action in ("box.disposed", "box.disposal_released"):
        verb = "hủy" if action == "box.disposed" else "hoàn"
        label = "Xuất hủy" if action == "box.disposed" else "Hoàn xuất hủy"
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"{verb} {qty(p.get('taken'))}")] if p.get("taken") is not None else [],
                     [part(f"thùng còn {qty(p.get('remaining'))}")] if p.get("remaining") is not None else [],
                     [part(f"phiếu hủy #{p.get('disposal_id')} →", href_for("disposal", p.get("disposal_id")))] if p.get("disposal_id") else [],
                     [part(f"“{str(p.get('disposal_reason')).strip()}”")] if str(p.get("disposal_reason") or "").strip() else []])
        return label, seg
    if action == "box.deleted":
        return "Xoá thùng khỏi kho", _inv_box_parts(p, resolver)
    if action in ("box.transfer_out", "box.transfer_in"):
        out = action == "box.transfer_out"
        peer_code = p.get("to_box") or p.get("to_code") if out else p.get("from_box") or p.get("from_code")
        place = p.get("to_name") if out else p.get("from_name")
        seg = _join([_inv_box_parts(p, resolver),
                     [part(f"{'chuyển' if out else 'nhận'} {qty(p.get('quantity'))}")],
                     [part(("→ " if out else "từ ") + f"thùng {boxnum(peer_code)}" + (f" ở {place}" if place else ""))]])
        return ("Chuyển hàng sang thùng khác" if out else "Nhận hàng từ thùng khác"), seg

    # ── SẢN XUẤT (event Telegram đã mang payload['detail'] sẵn) ─────────────
    if action == "production.created":
        return "Tạo phiếu SX", []
    if action in ("production.sp_changed", "production.target_changed",
                  "production.report_saved", "production.deleted_tg", "customer.edited"):
        label = {"production.sp_changed": "Đổi sản phẩm (Telegram)",
                 "production.target_changed": "Đặt chỉ tiêu (Telegram)",
                 "production.report_saved": "Lưu báo cáo thợ (Telegram)",
                 "production.deleted_tg": "Xoá phiếu (Telegram)",
                 "customer.edited": "Sửa khách (Telegram)"}[action]
        return label, [part(str(p.get("detail") or "")[:80])] if p.get("detail") else []

    # ── TRẢ HÀNG / NHẬP HÀNG / NCC ─────────────────────────────────────────
    if action == "return.goods_handled":
        res = p.get("result") or {}
        ne, nn, nd = len(res.get("restocked_existing") or []), len(res.get("restocked_new") or []), len(res.get("disposed") or [])
        bits = []
        if ne:
            bits.append([part(f"nhập {ne} thùng có sẵn")])
        if nn:
            bits.append([part(f"tạo {nn} thùng mới")])
        if nd:
            seg_d = [part(f"hủy {nd} mục →", href_for("disposal", res.get("disposal_id")))] if res.get("disposal_id") else [part(f"hủy {nd} mục")]
            bits.append(seg_d)
        return "Xử lý hàng trả về", _join(bits)
    if action.startswith("return."):
        label = {"return.created": "Tạo phiếu trả hàng", "return.invoiced": "Tạo HĐ KiotViet (trừ nợ)",
                 "return.invoice_deleted": "Xoá HĐ KiotViet (hoàn nợ)", "return.deleted": "Xoá phiếu trả"}.get(action)
        if not label:
            return None
        seg = _join([[customer_part(p["customer_key"], resolver)] if p.get("customer_key") else [],
                     [part(money(p.get("total")))] if p.get("total") is not None else [],
                     [part(f"HĐ {p.get('kv_code')}")] if p.get("kv_code") else []])
        return label, seg
    if action == "purchase.goods_received":
        res = p.get("result") or {}
        ne, nn = len(res.get("restocked_existing") or []), len(res.get("restocked_new") or [])
        bits = []
        if ne:
            bits.append([part(f"nhập {ne} thùng có sẵn")])
        if nn:
            bits.append([part(f"tạo {nn} thùng mới")])
        if not bits:
            bits.append([part("không nhập kho mục nào")])
        return "Nhập kho hàng mua về", _join(bits)
    if action == "purchase.goods_undone":
        seg = _join([[part(f"giữ {p.get('retained_boxes')} thùng")] if p.get("retained_boxes") else [],
                     [part(f"gỡ {p.get('removed_allocations')} lần cộng kho")] if p.get("removed_allocations") else []])
        return "Hủy chốt nhập kho hàng mua", seg
    if action == "purchase.goods_line_added":
        seg = [part(f"{p.get('boxes')} thùng")] if p.get("boxes") else []
        return "Ghi nhập kho hàng mua (chưa chốt)", seg
    if action == "purchase.goods_line_removed":
        seg = _join([[part(f"thùng {p.get('box_code')}")] if p.get("box_code") else [],
                     [part(f"−{p.get('quantity'):g}")] if p.get("quantity") else []])
        return "Gỡ dòng nhập kho hàng mua", seg
    if action in ("purchase.created", "purchase.deleted"):
        name = resolver.supplier_name(p.get("supplier_id")) if resolver else None
        seg = _join([[part(name or f"NCC #{p.get('supplier_id')}", href_for("supplier", p.get("supplier_id")))] if p.get("supplier_id") else [],
                     [part(money(p.get("total")))] if p.get("total") is not None else []])
        return ("Tạo phiếu nhập hàng" if action.endswith("created") else "Xoá phiếu nhập hàng"), seg
    if action in ("purchase.paid", "purchase.payment_deleted"):
        from cashbox_store.identity import box_display
        seg = _join([[part(money(p.get("amount")))] if p.get("amount") is not None else [],
                     [part(f"từ két {box_display(str(p.get('box')))}", "#/ket")] if p.get("box") else []])
        return ("Trả tiền nhập hàng" if action == "purchase.paid" else "Gỡ lần trả tiền nhập hàng"), seg
    if action in ("supplier.created", "supplier.deleted"):
        return ("Tạo nhà cung cấp" if action.endswith("created") else "Xoá nhà cung cấp"), \
            [part(str(p.get("name") or ""))] if p.get("name") else []

    # ── SẢN PHẨM ───────────────────────────────────────────────────────────
    if action.startswith("product."):
        label = {"product.created": "Tạo sản phẩm", "product.renamed": "Đổi mã SP",
                 "product.deleted": "Xoá sản phẩm", "product.linked": "Liên kết KiotViet",
                 "product.unlinked": "Gỡ liên kết KiotViet", "product.updated": "Sửa sản phẩm",
                 "product.unit_added": "Thêm đơn vị quy đổi", "product.unit_updated": "Sửa đơn vị quy đổi",
                 "product.unit_deleted": "Xoá đơn vị quy đổi"}.get(action)
        if not label:
            return None
        if action == "product.renamed":
            return label, [part(str(p.get("old_code") or "")), part(" → "),
                           _sp(p.get("new_code"), resolver)]
        if action.startswith("product.unit_"):
            # "1 thùng = 30 cây" — factor theo đơn vị gốc snapshot lúc ghi
            seg = _join([[_sp(p.get("code"), resolver)] if p.get("code") else [],
                         [part(f"1 {p.get('unit')} = {qty(p.get('factor'))} {p.get('base_unit') or ''}".strip())]
                         if p.get("unit") else []])
            return label, seg
        return label, [_sp(p.get("code"), resolver)] if p.get("code") else []

    # ── QUỸ / XUẤT HỦY / KIỂM KHO / CÀI ĐẶT ────────────────────────────────
    if action in ("quy.created", "quy.deleted"):
        t = {"thu": "thu", "chi": "chi"}.get(str(p.get("type") or "").lower(), str(p.get("type") or ""))
        seg = _join([[part(f"{t} {money(p.get('amount'))}")],
                     [part(str(p.get("note") or "")[:60])] if p.get("note") else []])
        return ("Thu/chi quỹ" if action == "quy.created" else "Xoá phiếu quỹ"), seg
    if action == "disposal.created":
        items = p.get("items") or []
        seg = _join([[part(f"“{str(p.get('reason') or '').strip()}”")] if str(p.get("reason") or "").strip() else [],
                     [part(f"hủy {qty(p.get('total_quantity'))}")] if p.get("total_quantity") is not None else [],
                     [part(f"{len(items)} mục")] if items else []])
        return "Tạo phiếu xuất hủy", seg
    if action == "disposal.deleted":
        ra = p.get("restored_allocations")
        # emitter ghi SỐ LƯỢNG (int) — bản cũ từng ghi list; nhận cả 2
        n = ra if isinstance(ra, (int, float)) else len(ra or []) or len(p.get("items") or [])
        n = int(n or 0)
        return "Xoá phiếu hủy (hoàn tồn)", [part(f"hoàn {n} phần về thùng")] if n else []
    if action.startswith("stocktake."):
        _st_labels = {
            "stocktake.created": "Tạo phiếu kiểm kho",
            "stocktake.completed": "Hoàn tất kiểm kho",
            "stocktake.resynced": "Cập nhật lại phiếu kiểm kho",
            "stocktake.voided": "Huỷ phiếu kiểm kho",
            "stocktake.applied": "Áp dụng kiểm kho vào kho",
        }
        label = _st_labels.get(action)
        if label:
            seg = _join([[part(f"phiếu #{p.get('stocktake_id')} →", href_for("stocktake", p.get("stocktake_id")))] if p.get("stocktake_id") else [],
                         [part(f"{p.get('box_count')} thùng")] if p.get("box_count") is not None else [],
                         [part(f"điều chỉnh {p.get('adjusted')} thùng lệch")] if p.get("adjusted") is not None else []])
            return label, seg
    # ── PHIẾU ĐIỀU CHỈNH tồn thùng (adjustment.*) — scope='box' ────────────────
    if action in ("adjustment.created", "adjustment.deleted"):
        d = p.get("delta")
        rem = p.get("remaining", p.get("new_remaining"))   # payload mới: remaining SAU biến động
        seg = _join([[box_part(p.get("box_id"), p.get("box_code"), resolver)] if p.get("box_code") or p.get("box_id") else [],
                     [_sp(p.get("product_code"), resolver)] if p.get("product_code") else [],
                     [part(f"{float(d):+g}")] if d is not None else [],
                     [part(f"thùng còn {qty(rem)}")] if rem is not None else [],
                     [part(f"“{str(p.get('reason') or '')[:60]}”")] if p.get("reason") else []])
        return ("Điều chỉnh tồn thùng" if action == "adjustment.created"
                else "Gỡ phiếu điều chỉnh (hoàn nguyên)"), seg
    if action == "settings.changed":
        k = str(p.get("key") or "")
        v = p.get("value")
        vi = _SETTING_VI.get(k, k)
        val = "BẬT" if v in (True, "true", 1) else ("TẮT" if v in (False, "false", 0) else str(v))
        return "Đổi cài đặt hệ thống", [part(f"{vi}: {val}")]
    return None
