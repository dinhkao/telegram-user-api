"""So sánh TRƯỚC/SAU của 1 đơn → danh sách thay đổi (nhãn, cũ→mới) cho lịch sử.

Chỉ soi các TRƯỜNG QUAN TRỌNG với người dùng (khách, hóa đơn/sản phẩm, tiền,
công việc, nội dung, nợ) — trường kỹ thuật (channel_id, flow_version, updated_at…)
bị bỏ qua. Thuần (không IO) → unit-test ở tests/test_order_diff.py.
Dùng bởi: server_app/audit.py (chụp snapshot quanh mỗi POST sửa đơn) +
server_app/order_history.py (đọc lại để hiển thị).
"""
from __future__ import annotations

import re

# Các path POST làm THAY ĐỔI dữ liệu đơn (chuẩn hoá {id}) — chỉ những path này mới
# được chụp snapshot trước/sau. Read-only (reply/refresh-view/totals/preview) loại ra.
_MUTATION_PATHS = {
    "/api/order/task", "/api/order/soan", "/api/order/ban", "/api/order/giao",
    "/api/order/nop-tien", "/api/order/{id}/task_status/clear",
    "/api/order/invoice/create-kiotviet", "/api/order/invoice/delete-kiotviet",
    "/api/order/invoice/update", "/api/order/payment/tm", "/api/order/payment/ck",
    "/api/order/payment/delete", "/api/order/assign-customer",
    "/api/order/refresh-debt", "/api/order/fix", "/api/order/auto-parse",
    "/api/order/ngay-giao", "/api/order/no-track", "/api/order/bypass-debt",
    "/api/order/{id}/custom-task", "/api/order/{id}/custom-task/remove",
    "/api/order/{id}/stock-confirm", "/api/order/{id}",
}
_ID_RE = re.compile(r"/api/order/-?\d+")

_TASK_VI = {
    "soan_hang": "Soạn hàng", "ban_hd": "Bán hóa đơn", "giao_hang": "Giao hàng",
    "nop_tien": "Nộp tiền", "nhan_tien": "Nhận tiền",
}
_METHOD_VI = {"Cash": "tiền mặt", "Transfer": "chuyển khoản", "TM": "tiền mặt", "CK": "chuyển khoản"}


def is_order_mutation(method: str, path: str) -> bool:
    """Request này có làm thay đổi blob đơn không (để chụp snapshot)."""
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return _ID_RE.sub("/api/order/{id}", path) in _MUTATION_PATHS


def _money(v) -> str:
    try:
        return f"{int(v):,}đ".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def _norm_money(v):
    """Chuẩn hóa để so sánh: trống/None coi như 0 (nên 'trống → 0đ' KHÔNG phải thay đổi)."""
    if v in (None, ""):
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _yes_no(v) -> str:
    return "Có" if v in (True, 1, "1", "true") else "Không"


def _stock_confirm(v) -> str:
    return "Đã chốt" if isinstance(v, dict) or v in (True, 1, "1", "true") else "Chưa chốt"


def _short(s, n: int = 45) -> str:
    s = "" if s is None else str(s)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def _task_state(entry) -> str:
    if not isinstance(entry, dict) or not (entry.get("done") or entry.get("skip")):
        return "chưa"
    if entry.get("skip"):
        return "bỏ qua"
    return "đã xong"


def _inv_map(order: dict) -> dict:
    out = {}
    for it in (order.get("invoice") or []):
        if isinstance(it, dict) and it.get("sp"):
            out[str(it["sp"])] = it
    return out


def _pay_map(order: dict) -> dict:
    out = {}
    for p in (order.get("payments") or []):
        if isinstance(p, dict):
            out[str(p.get("id") or id(p))] = p
    return out


def _chg(label: str, old, new) -> dict:
    return {"label": label, "old": "" if old is None else str(old), "new": "" if new is None else str(new)}


# Trường vô hướng đơn giản: (khóa blob, nhãn, hàm format)
_SCALARS = [
    ("customer_name", "Khách hàng", str),
    ("khach_hang_id", "Mã khách hàng", str),
    ("kiotvietInvoiceCode", "Mã hóa đơn KiotViet", str),
    ("vat", "VAT", _money),
    ("pvc", "Phụ phí (PVC)", _money),
    ("discount", "Giảm giá", _money),
    ("khDebt", "Nợ khách", _money),
    ("invoice_debt_snapshot", "Nợ tại hóa đơn", _money),
    ("ngay_giao", "Ngày giao", str),
    ("bo_theo_doi_no", "Bỏ theo dõi nợ", _yes_no),
    ("bypass_debt", "Ẩn khi thu tiền", _yes_no),
    ("stock_confirmed", "Chốt xuất kho", _stock_confirm),
]


def diff_changes(before: dict | None, after: dict | None) -> list[dict]:
    """So sánh 2 blob đơn → [{label, old, new}] các trường quan trọng đã đổi."""
    before = before or {}
    after = after or {}
    if not after:
        return []
    changes: list[dict] = []

    # Nội dung đơn (rút gọn để không tràn)
    if before.get("text") != after.get("text") and (before.get("text") or after.get("text")):
        changes.append(_chg("Nội dung đơn", _short(before.get("text")) or "(trống)", _short(after.get("text")) or "(trống)"))

    # Trường vô hướng (tiền/mã/khách)
    for key, label, fmt in _SCALARS:
        o, n = before.get(key), after.get(key)
        # Tiền: coi trống==0 để bỏ nhiễu "(trống) → 0đ" (không phải thay đổi thật)
        if _norm_money(o) == _norm_money(n) if fmt is _money else o == n:
            continue
        changes.append(_chg(label, fmt(o) if o not in (None, "") else "(trống)", fmt(n) if n not in (None, "") else "(trống)"))

    # Hóa đơn: so từng sản phẩm theo mã (SL / giá)
    ob, nb = _inv_map(before), _inv_map(after)
    for sp in sorted(set(ob) | set(nb)):
        o, n = ob.get(sp), nb.get(sp)
        if o and not n:
            changes.append(_chg(f"SP {sp}", f"{o.get('sl', '?')} cây", "(xóa)"))
        elif n and not o:
            changes.append(_chg(f"SP {sp}", "(thêm)", f"{n.get('sl', '?')} cây × {_money(n.get('price'))}"))
        else:
            if o.get("sl") != n.get("sl"):
                changes.append(_chg(f"SP {sp} — số lượng", f"{o.get('sl', '?')} cây", f"{n.get('sl', '?')} cây"))
            if o.get("price") != n.get("price"):
                changes.append(_chg(f"SP {sp} — giá", _money(o.get("price")), _money(n.get("price"))))

    # Thanh toán: thêm/xóa theo id
    op, np_ = _pay_map(before), _pay_map(after)
    for pid in np_.keys() - op.keys():
        p = np_[pid]
        changes.append(_chg("Thu tiền", "", f"{_money(p.get('amount'))} ({_METHOD_VI.get(str(p.get('method')), p.get('method') or '')})"))
    for pid in op.keys() - np_.keys():
        p = op[pid]
        changes.append(_chg("Xóa thanh toán", f"{_money(p.get('amount'))} ({_METHOD_VI.get(str(p.get('method')), p.get('method') or '')})", ""))

    # Công việc: theo từng bước (soạn/bán/giao/nộp/nhận)
    ots, nts = before.get("task_status") or {}, after.get("task_status") or {}
    custom_labels = {}
    for item in (before.get("custom_tasks") or []) + (after.get("custom_tasks") or []):
        if isinstance(item, dict) and item.get("id"):
            custom_labels[str(item["id"])] = str(item.get("label") or item["id"])
    for step in sorted(set(ots) | set(nts)):
        o, n = ots.get(step), nts.get(step)
        os_, ns_ = _task_state(o), _task_state(n)
        if os_ != ns_:
            changes.append(_chg(_TASK_VI.get(step, custom_labels.get(step, step)), os_, ns_))

    # Định nghĩa việc tùy chỉnh có thể được thêm/xóa khi chưa có task_status.
    old_defs = {str(x.get("id")): str(x.get("label") or "") for x in (before.get("custom_tasks") or []) if isinstance(x, dict) and x.get("id")}
    new_defs = {str(x.get("id")): str(x.get("label") or "") for x in (after.get("custom_tasks") or []) if isinstance(x, dict) and x.get("id")}
    for task_id in new_defs.keys() - old_defs.keys():
        changes.append(_chg("Việc tùy chỉnh", "", f"Thêm: {new_defs[task_id]}"))
    for task_id in old_defs.keys() - new_defs.keys():
        changes.append(_chg("Việc tùy chỉnh", f"Xóa: {old_defs[task_id]}", ""))

    return changes
