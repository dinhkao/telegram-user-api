"""Luật thuần GIẤY DÁN THÙNG của 1 đơn (không IO) — dùng bởi server_app/gdt_routes.py
và command_handlers/gdt_handler.py. Dữ liệu nằm ở blob đơn `$.giay_dan_thung`
= {ten_gdt, sdt_gdt, so_thung, note_gdt} (giữ nguyên key của lệnh Telegram `gdt`
cũ để 2 đường ghi/đọc chung 1 chỗ). Cache theo khách: `$.gdt_contact` blob customers.
"""
from __future__ import annotations

import re

GDT_KEYS = ("ten_gdt", "sdt_gdt", "so_thung", "note_gdt")
_BODY_ALIASES = {"ten": "ten_gdt", "sdt": "sdt_gdt", "so_thung": "so_thung", "note": "note_gdt"}
_MAX_LEN = 120


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:_MAX_LEN]


def normalize_body(body: dict) -> tuple[dict | None, str | None]:
    """Body web {ten, sdt, so_thung, note} (hoặc key blob) → dict blob chuẩn.
    Trả (gdt, None) hoặc (None, lỗi). Bắt buộc: tên người nhận + số thùng."""
    body = body or {}
    gdt = {}
    for short, key in _BODY_ALIASES.items():
        gdt[key] = _clean(body.get(short, body.get(key)))
    if not gdt["ten_gdt"]:
        return None, "Thiếu tên người nhận"
    if not gdt["so_thung"]:
        return None, "Thiếu số thùng"
    return gdt, None


def gdt_of(order: dict | None) -> dict | None:
    """Giấy dán thùng đã lưu của đơn (None nếu chưa có / hỏng)."""
    g = (order or {}).get("giay_dan_thung")
    if not isinstance(g, dict):
        return None
    out = {k: _clean(g.get(k)) for k in GDT_KEYS}
    return out if out["ten_gdt"] or out["so_thung"] else None


def fmt_thu_ho(amount) -> str:
    """'Thu hộ 700,000' — dấu phẩy nghìn như mẫu in cũ; ≤ 0 → ''."""
    try:
        n = int(round(float(amount or 0)))
    except (TypeError, ValueError):
        return ""
    return f"Thu hộ {n:,}" if n > 0 else ""


def build_prefill(order: dict | None, customer: dict | None, remaining) -> dict:
    """Điền sẵn form: bản đã lưu của đơn thắng; chưa có thì tên/SĐT lấy từ lần
    dán thùng gần nhất của KHÁCH (`gdt_contact`), rồi tên khách; ghi chú gợi ý
    'Thu hộ <còn phải thu>' khi đơn còn nợ."""
    saved = gdt_of(order)
    if saved:
        return dict(saved)
    contact = (customer or {}).get("gdt_contact") if isinstance(customer, dict) else None
    contact = contact if isinstance(contact, dict) else {}
    ten = _clean(contact.get("ten")) or _clean((customer or {}).get("name")) \
        or _clean((order or {}).get("customer_name") or (order or {}).get("kh"))
    return {
        "ten_gdt": ten,
        "sdt_gdt": _clean(contact.get("sdt")),
        "so_thung": "",
        "note_gdt": fmt_thu_ho(remaining),
    }


def contact_from(gdt: dict) -> dict:
    """Phần nhớ theo khách sau khi lưu (tên + SĐT người nhận)."""
    return {"ten": gdt.get("ten_gdt", ""), "sdt": gdt.get("sdt_gdt", "")}


def summary(gdt: dict) -> str:
    """1 dòng tóm tắt cho lịch sử/thông báo: 'Tên · SĐT · 3 thùng · Thu hộ 700,000'."""
    parts = [gdt.get("ten_gdt", "")]
    if gdt.get("sdt_gdt"):
        parts.append(gdt["sdt_gdt"])
    if gdt.get("so_thung"):
        parts.append(f"{gdt['so_thung']} thùng")
    if gdt.get("note_gdt"):
        parts.append(gdt["note_gdt"])
    return " · ".join(p for p in parts if p)
