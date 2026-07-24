"""Parse/format SỐ LƯỢNG hoá đơn — sl có thể LẺ (vd 3,5 thùng). Dùng chung mọi
đường tiền (KiotViet, render Telegram, tổng đơn, feed nợ) để không nơi nào cắt
``int(sl)`` làm mất phần lẻ (đơn 3,5 thùng bị tính tiền 3 thùng — mất doanh thu).
Leaf module: không import gì ngoài stdlib.
"""
import math


def parse_qty(value) -> float:
    """SL từ blob: số hoặc chuỗi ('3', '3.5', '3,5', '1.234' kiểu nghìn).

    Chuỗi: ',' coi là dấu THẬP PHÂN (kiểu VN); nhiều dấu '.' = phân cách nghìn
    → bỏ hết. NaN/Infinity/lỗi → 0.0 (không để lọt vào tổng tiền).
    """
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, str):
            s = value.strip().replace(",", ".")
            if s.count(".") > 1:          # '1.234.567' = phân cách nghìn
                s = s.replace(".", "")
            value = s
        q = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(q):
        return 0.0
    return q


def qty_for_api(value, default: float = 0.0):
    """SL gửi API ngoài (KiotViet): int khi chẵn, float làm tròn 3 chữ số khi lẻ."""
    q = parse_qty(value)
    if q == 0.0 and default:
        q = float(default)
    if q == int(q):
        return int(q)
    return round(q, 3)


def fmt_qty(value) -> str:
    """Hiển thị SL: 3 → '3', 3.5 → '3,5' (kiểu VN)."""
    q = parse_qty(value)
    if q == int(q):
        return str(int(q))
    return f"{q:g}".replace(".", ",")


def line_total(price, sl) -> int:
    """Tiền 1 dòng hoá đơn = giá × SL, làm tròn về ĐỒNG (int)."""
    try:
        p = float(price or 0)
    except (TypeError, ValueError):
        p = 0.0
    if not math.isfinite(p):
        p = 0.0
    return round(p * parse_qty(sl))
