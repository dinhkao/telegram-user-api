"""Bảng LƯƠNG theo sản phẩm (đơn giá / 1 cây SP) — cho dashboard tiền công thợ.

NHẠY CẢM: chỉ dùng ở endpoint đã chặn role văn phòng (server_app/production_wages).
Tiền công 1 thợ 1 ngày = Σ (số cây SP đó thợ làm × luong[SP]). `mam`/`chao` giữ
tham khảo (số cây 1 mâm / 1 chảo), không dùng để tính tiền. Khớp theo MÃ HIỆN HÀNH
(resolve product_id ở query) — đổi mã vẫn đúng. SP không có trong bảng → lương 0
(không tính tiền, được liệt kê ở `missing_wage` để văn phòng biết cần bổ sung).
"""
from __future__ import annotations

# code (mã hiện hành, IN HOA) → {mam: số cây 1 mâm, chao: số cây 1 chảo | None, luong: đồng / 1 cây}
WAGES: dict[str, dict] = {
    "K10LT":    {"mam": 3.0, "chao": 18.0, "luong": 1200},
    "K10LV85":  {"mam": 3.0, "chao": 25.0, "luong": 1000},
    "K10LV87":  {"mam": 3.0, "chao": 19.0, "luong": 1100},
    "K10NV60":  {"mam": 5.0, "chao": None, "luong": 500},
    "K10TV80":  {"mam": 4.0, "chao": 26.0, "luong": 800},
    "K2L":      {"mam": 3.5, "chao": 31.0, "luong": 720},
    "K2NT":     {"mam": 6.0, "chao": 38.0, "luong": 420},
    "K2NV120":  {"mam": 6.0, "chao": 54.0, "luong": 380},
    "K2NV128":  {"mam": 6.0, "chao": 47.0, "luong": 380},
    "KDDT":     {"mam": 5.0, "chao": None, "luong": 800},
    "KE":       {"mam": 6.0, "chao": None, "luong": 500},
    "KHT":      {"mam": 8.0, "chao": None, "luong": 400},
    "K13NV-58": {"mam": 4.0, "chao": None, "luong": 750},
    "KD2M":     {"mam": 6.0, "chao": 41.0, "luong": 900},
    "KDBN2M":   {"mam": 4.5, "chao": 30.0, "luong": 1000},
    "KDBN1L":   {"mam": 4.0, "chao": 28.0, "luong": 1000},
    "K1L":      {"mam": 4.0, "chao": 25.0, "luong": 720},
    "K2LBN":    {"mam": 3.5, "chao": 31.0, "luong": 720},
    # KDT / TL: chưa có đơn giá → không tính tiền (nằm trong missing_wage)
}


def wage_per_cay(code: str | None) -> float:
    """Đơn giá lương / 1 cây của SP (0 nếu chưa có trong bảng)."""
    return float(WAGES.get(str(code or "").strip().upper(), {}).get("luong") or 0)


def has_wage(code: str | None) -> bool:
    return wage_per_cay(code) > 0
