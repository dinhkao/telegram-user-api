"""Quy cách đóng gói cho parser hoá đơn — số cái / 1 thùng (t), 1 bịch (b) theo mã SP,
và luật lốc DM180. Trước đây HARDCODE trong order_store.free_text; giờ admin sửa được
từ webapp (#/quy-cach) → lưu settings_store['parse_quy_cach']. Đọc qua load_quy_cach
(có cache TTL vì parse chạy nhiều lúc gõ preview). Nối: settings_store; dùng bởi
order_store.free_text, server_app.quy_cach_routes.
"""
from __future__ import annotations

import time

# Mặc định = đúng các hằng cũ trong free_text.py (giữ nguyên hành vi khi chưa cấu hình).
DEFAULTS: dict = {
    "thung_base": 50,          # 1 thùng mặc định = 50 cái
    "bich_base": 10,           # 1 bịch mặc định = 10 cái ("2b = 20", base 10)
    "thung_overrides": {       # số cái / 1 thùng theo mã SP (đè thung_base)
        "DM50": 100,
        "KDXDB": 5, "KGL": 5, "KMT": 5, "KMD": 5, "KHDX": 5,
        "KDDT": 12,
    },
    "bich_overrides": {"KDDT": 3},   # số cái / 1 bịch theo mã SP (đè bich_base)
    "dm180_loc": 12,           # "dm180 N lốc" = N bịch × 12
}

_SETTINGS_KEY = "parse_quy_cach"
_TTL = 30.0
_cache: dict = {"cfg": None, "exp": 0.0}


def _pos_int(v, fallback: int) -> int:
    """Ép về int > 0; giá trị xấu/≤0 → fallback."""
    try:
        n = int(v)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _clean_overrides(raw) -> dict:
    """Chuẩn hoá dict override: KEY = mã in HOA, VALUE = int > 0 (bỏ dòng xấu)."""
    out: dict[str, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            code = str(k or "").strip().upper()
            if not code:
                continue
            try:
                n = int(v)
            except (TypeError, ValueError):
                continue
            if n > 0:
                out[code] = n
    return out


def normalize(raw) -> dict:
    """Trộn cấu hình người dùng lên DEFAULTS, chuẩn hoá kiểu. Override dict thay THẾ
    trọn (thiếu key = dùng bảng mặc định; có key = dùng đúng bảng người dùng gửi)."""
    raw = raw if isinstance(raw, dict) else {}
    cfg = {
        "thung_base": _pos_int(raw.get("thung_base"), DEFAULTS["thung_base"]),
        "bich_base": _pos_int(raw.get("bich_base"), DEFAULTS["bich_base"]),
        "dm180_loc": _pos_int(raw.get("dm180_loc"), DEFAULTS["dm180_loc"]),
        "thung_overrides": _clean_overrides(raw["thung_overrides"]) if "thung_overrides" in raw else dict(DEFAULTS["thung_overrides"]),
        "bich_overrides": _clean_overrides(raw["bich_overrides"]) if "bich_overrides" in raw else dict(DEFAULTS["bich_overrides"]),
    }
    return cfg


def load_quy_cach(conn=None) -> dict:
    """Cấu hình quy cách HIỆN HÀNH (đã trộn mặc định). Cache TTL 30s (parse gọi nhiều
    lúc gõ preview) — invalidate khi lưu. conn: tái dùng nếu có (khỏi mở connection)."""
    now = time.monotonic()
    if _cache["cfg"] is not None and now < _cache["exp"]:
        return _cache["cfg"]
    from settings_store import get_all
    raw = get_all(conn).get(_SETTINGS_KEY)
    cfg = normalize(raw)
    _cache["cfg"] = cfg
    _cache["exp"] = now + _TTL
    return cfg


def invalidate_cache() -> None:
    _cache["cfg"] = None
    _cache["exp"] = 0.0


def thung_qty(sp: str, cfg: dict) -> int:
    """Số cái / 1 thùng cho mã sp (override → base)."""
    return cfg["thung_overrides"].get(str(sp or "").upper(), cfg["thung_base"])


def bich_qty(sp: str, cfg: dict) -> int:
    """Số cái / 1 bịch cho mã sp (override → base)."""
    return cfg["bich_overrides"].get(str(sp or "").upper(), cfg["bich_base"])
