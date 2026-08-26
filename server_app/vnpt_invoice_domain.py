"""Logic thuần hoá đơn nháp VNPT: validate body, prefill từ cache khách.

Không IO — unit-tested (tests/test_vnpt_invoice_domain.py). IO nằm ở
server_app/vnpt_invoice_routes.py. Cache theo khách = key `vnpt_profile` trong
blob customers: {buyer, vat_rate, products: {sp_id|"code:MÃ": {name, unit,
price}}, extra_lines: [...]} — lần sau tạo HĐ cho khách đó là tự điền, khỏi gõ
lại (Duy yêu cầu 2026-08-26; tên/giá/ĐVT trên HĐ được phép KHÁC dữ liệu đơn).
"""
from __future__ import annotations

import re

from integrations.vnpt_invoice import VAT_RATES

# MST Việt Nam: 10 số (số thứ 10 = số KIỂM TRA), hoặc 10 số + "-" + 3 số (đơn vị
# phụ thuộc). VNPT ÂM THẦM BỎ TRỐNG MST sai checksum trên hoá đơn (thực nghiệm
# 2026-08-26) → phải chặn ở đây cho người dùng biết ngay.
_MST_RE = re.compile(r"(\d{10})(?:-(\d{3}))?")
_MST_WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


def mst_valid(mst: str) -> bool:
    m = _MST_RE.fullmatch(mst)
    if not m:
        return False
    d = [int(c) for c in m.group(1)]
    s = sum(w * x for w, x in zip(_MST_WEIGHTS, d[:9]))
    return d[9] == 10 - (s % 11)

_BUYER_KEYS = (
    "cus_name", "buyer_name", "tax_code", "address", "phone",
    "email", "payment_method",
)
# email nhận hoá đơn: cho nhiều địa chỉ cách nhau ; hoặc ,
_EMAIL_RE = re.compile(r"[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+")
DEFAULT_VAT_RATE = 8


def normalize_body(body: dict) -> tuple[dict, list[dict], int]:
    """Body POST → (buyer, lines, vat_rate) sạch. Sai → ValueError (message VN)."""
    buyer_in = body.get("buyer") or {}
    if not isinstance(buyer_in, dict):
        raise ValueError("buyer không hợp lệ")
    buyer = {}
    for k in _BUYER_KEYS:
        v = str(buyer_in.get(k) or "").strip()
        if len(v) > 500:
            raise ValueError(f"trường {k} quá dài")
        buyer[k] = v
    # BẮT BUỘC: MST + tên đơn vị + địa chỉ (Duy chốt 2026-08-26)
    if not buyer["cus_name"]:
        raise ValueError("thiếu tên đơn vị (bắt buộc)")
    if not buyer["address"]:
        raise ValueError("thiếu địa chỉ (bắt buộc)")
    mst = buyer["tax_code"].replace(" ", "")
    if not mst:
        raise ValueError("thiếu mã số thuế (bắt buộc)")
    if not mst_valid(mst):
        raise ValueError(
            "mã số thuế không hợp lệ (sai số kiểm tra) — kiểm lại MST của khách; "
            "MST sai VNPT sẽ bỏ trống trên hoá đơn")
    buyer["tax_code"] = mst
    # Email nhận hoá đơn: TUỲ CHỌN; có nhập thì từng địa chỉ phải đúng dạng
    if buyer["email"]:
        parts = [p.strip() for p in re.split(r"[;,]", buyer["email"]) if p.strip()]
        if not parts or any(not _EMAIL_RE.fullmatch(p) for p in parts):
            raise ValueError("email nhận hoá đơn không hợp lệ")
        buyer["email"] = ";".join(parts)

    raw_lines = body.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValueError("hoá đơn không có dòng hàng nào")
    lines: list[dict] = []
    for i, ln in enumerate(raw_lines, 1):
        if not isinstance(ln, dict):
            raise ValueError(f"dòng {i} không hợp lệ")
        name = str(ln.get("name") or "").strip()
        if not name:
            raise ValueError(f"dòng {i} thiếu tên hàng")
        try:
            qty = float(ln.get("qty"))
            price = int(ln.get("price"))
        except (TypeError, ValueError):
            raise ValueError(f"dòng {i}: SL/đơn giá không hợp lệ")
        if qty <= 0:
            raise ValueError(f"dòng {i}: SL phải > 0")
        if price < 0:
            raise ValueError(f"dòng {i}: đơn giá âm")
        out = {"name": name, "unit": str(ln.get("unit") or "").strip(),
               "qty": qty, "price": price}
        try:
            if ln.get("sp_id"):
                out["sp_id"] = int(ln["sp_id"])
        except (TypeError, ValueError):
            pass
        lines.append(out)

    try:
        vat_rate = int(body.get("vat_rate"))
    except (TypeError, ValueError):
        raise ValueError("thiếu thuế suất")
    if vat_rate not in VAT_RATES:
        raise ValueError(f"thuế suất không hợp lệ: {vat_rate}")
    return buyer, lines, vat_rate


def _template_for(templates: dict, item: dict) -> dict | None:
    spid = item.get("sp_id")
    if spid and str(spid) in templates:
        return templates[str(spid)]
    code = str(item.get("sp") or "").strip().upper()
    return templates.get(f"code:{code}") if code else None


def build_prefill(order: dict, customer: dict | None,
                  unit_by_spid: dict[int, str]) -> dict:
    """Điền sẵn form tạo HĐ: cache khách (vnpt_profile) đè lên dữ liệu đơn/SP."""
    customer = customer or {}
    profile = customer.get("vnpt_profile") or {}
    templates = profile.get("products") or {}
    buyer = dict(profile.get("buyer") or {})
    if not buyer.get("cus_name"):
        buyer["cus_name"] = str(customer.get("name") or "")
    buyer.setdefault("address", str(customer.get("address") or ""))
    buyer.setdefault("phone", str(customer.get("contactNumber") or ""))
    buyer.pop("cus_code", None)   # mã khách hàng — Duy bỏ 2026-08-26 (profile cũ có thì lọc)

    lines: list[dict] = []
    for it in order.get("invoice") or []:
        tpl = _template_for(templates, it) or {}
        spid = it.get("sp_id")
        ln = {
            "name": str(tpl.get("name") or it.get("name") or it.get("sp") or "").strip(),
            "unit": str(tpl.get("unit") or unit_by_spid.get(spid or 0) or "").strip(),
            "qty": float(it.get("sl") or 0) or 1,
            "price": int(tpl["price"]) if tpl.get("price") else int(it.get("price") or 0),
        }
        if spid:
            ln["sp_id"] = int(spid)
        lines.append(ln)
    # Dòng "thêm tay" của lần trước (không khớp SP nào của đơn) — điền lại luôn
    for ex in profile.get("extra_lines") or []:
        try:
            lines.append({
                "name": str(ex.get("name") or "").strip(),
                "unit": str(ex.get("unit") or "").strip(),
                "qty": float(ex.get("qty") or 1),
                "price": int(ex.get("price") or 0),
            })
        except (TypeError, ValueError):
            continue
    return {
        "buyer": buyer,
        "vat_rate": profile.get("vat_rate", DEFAULT_VAT_RATE),
        "lines": [ln for ln in lines if ln["name"]],
    }


def updated_profile(old_profile: dict | None, buyer: dict, lines: list[dict],
                    vat_rate: int) -> dict:
    """Hồ sơ vnpt_profile mới sau 1 lần lưu HĐ: buyer/vat_rate thay hẳn;
    products MERGE theo sp_id (SP không có trong HĐ này giữ template cũ);
    extra_lines (dòng không gắn sp_id) THAY HẲN — không cộng dồn vô hạn."""
    products = dict((old_profile or {}).get("products") or {})
    extra: list[dict] = []
    for ln in lines:
        tpl = {"name": ln["name"], "unit": ln.get("unit") or "",
               "price": int(ln.get("price") or 0)}
        if ln.get("sp_id"):
            products[str(int(ln["sp_id"]))] = tpl
        else:
            extra.append({**tpl, "qty": float(ln.get("qty") or 1)})
    return {"buyer": buyer, "vat_rate": vat_rate,
            "products": products, "extra_lines": extra}
