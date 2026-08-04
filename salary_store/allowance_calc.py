"""PHỤ CẤP TÍNH THEO CÔNG THỨC — logic thuần, không IO.

1 khoản phụ cấp có 3 dạng (cột `salary_allowances.calc_kind`):
- NULL/"" : SỐ TIỀN CỐ ĐỊNH — lấy nguyên `amount` như trước.
- "pct"   : % LƯƠNG GỐC của tháng — `calc_value`% × base.
- "day"   : ĐƠN GIÁ × NGÀY CÔNG — `calc_value`đ × số công của tháng.

⚠ 2 dạng có công thức được TÍNH LẠI MỖI LẦN XEM (2026-08-04, Duy chốt): sửa báo cáo
SX hay sửa chấm công thì phụ cấp tự chạy theo lương gốc mới. Cột `amount` với 2 dạng
này chỉ là số CHỤP LÚC NHẬP để hiển thị tạm khi chưa biết gốc — KHÔNG phải nguồn sự
thật, đừng cộng thẳng `amount` cho mọi dòng nữa.

LƯƠNG GỐC (base) tuỳ loại thợ, do chỗ gọi truyền vào:
- thợ lương SẢN PHẨM → lương sản phẩm của tháng,
- thợ lương THỜI GIAN → lương theo NGÀY CÔNG (cố ý KHÔNG gồm lương tăng ca).

Nối: salary_store.store (compute_month_payroll, list_allowances, add_allowance).
Tests: tests/test_allowance_calc.py.
"""
from __future__ import annotations

KIND_PCT = "pct"
KIND_DAY = "day"
KINDS = (KIND_PCT, KIND_DAY)


def allowance_amount(kind: str | None, value: float | None, amount: float, *,
                     base: float, cong: float) -> float:
    """Số tiền HIỆN TẠI của 1 khoản phụ cấp (đã làm tròn đồng).

    base = lương gốc của tháng (theo loại thợ), cong = số ngày công của tháng.
    Gốc âm/thiếu coi như 0 → khoản theo công thức ra 0 (không đoán, không âm)."""
    k = (kind or "").strip()
    if k == KIND_PCT:
        return round(max(0.0, float(base or 0)) * float(value or 0) / 100.0)
    if k == KIND_DAY:
        return round(float(value or 0) * max(0.0, float(cong or 0)))
    return round(float(amount or 0))


def calc_label(kind: str | None, value: float | None) -> str:
    """Nhãn ngắn mô tả công thức ("10% lương gốc", "20.000đ × ngày công"). Dạng cố
    định trả "" — không có công thức nào để nói."""
    k = (kind or "").strip()
    v = float(value or 0)
    num = f"{v:g}".replace(".", ",")
    if k == KIND_PCT:
        return f"{num}% lương gốc"
    if k == KIND_DAY:
        return f"{v:,.0f}đ × ngày công".replace(",", ".")
    return ""


def normalize(kind: str | None, value) -> tuple[str | None, float | None]:
    """Làm sạch (kind, value) trước khi ghi DB. Kind lạ / value ≤ 0 → (None, None)
    = quay về khoản TIỀN CỐ ĐỊNH, KHÔNG ném lỗi: nhập sai thì thà ghi cố định còn
    hơn chặn người dùng giữa chừng."""
    k = (kind or "").strip()
    if k not in KINDS:
        return None, None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, None
    if not (v > 0) or v != v or v in (float("inf"), float("-inf")):
        return None, None
    if k == KIND_PCT and v > 100:
        return None, None       # >100% lương chắc chắn là gõ nhầm
    return k, v
