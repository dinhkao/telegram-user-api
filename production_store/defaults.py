"""Mặc định sản xuất (mâm/lượng) của 1 SP — nguồn: cột products.prod_mam /
prod_luong (DB, port từ SP_INFO, sửa được qua danh mục) → fallback SP_INFO
(bot_core.config, legacy config cứng). Nhận cả mã cũ qua resolve.
Nối: product_store, bot_core.config."""
from __future__ import annotations


def production_defaults(conn, code) -> tuple:
    """(mam, luong) mặc định của mã SP — None nếu không biết."""
    from product_store import resolve_code
    prod = resolve_code(conn, code)
    mam = prod.get("prod_mam") if prod else None
    luong = prod.get("prod_luong") if prod else None
    if mam is None or luong is None:
        try:
            from bot_core.config import SP_INFO
        except Exception:  # noqa: BLE001
            SP_INFO = {}
        info = SP_INFO.get((prod or {}).get("code") or str(code or "").strip().upper(), {})
        if mam is None:
            mam = info.get("mam")
        if luong is None:
            luong = info.get("luong")
    return mam, luong
