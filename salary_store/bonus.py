"""2 khoản THƯỞNG bật/tắt theo tháng: CHUYÊN CẦN và VỆ SINH — logic thuần, không IO.

- Chuyên cần: bật là được ĐÚNG `THUONG_CHUYEN_CAN` (cố định, không phụ thuộc công).
- Vệ sinh: `THUONG_VE_SINH_MOI_NGAY` × SỐ NGÀY CÔNG của tháng — dùng đúng con số
  `cong` hiện ở cột Công của bảng lương (quy từ máy chấm công; thợ TG* thì `cong`
  đã gộp giờ tăng ca, xem compute_month_payroll) để người xem nhân nhẩm ra được.

Bật/tắt lưu ở `salary_month.thuong_cc` / `.thuong_vs`, **THEO TỪNG THÁNG và KHÔNG
kế thừa** — giống cờ `weekly` cùng bảng, KHÁC mốc lương / trừ BHXH (2 thứ đó kế
thừa). Cố ý: thưởng là quyết định của từng tháng; để nó tự bò sang tháng sau thì
tháng nào quên tắt là trả thừa tiền mà không ai thấy.

Muốn ĐỔI MỨC thưởng thì sửa 2 hằng số dưới đây (chưa có màn hình cấu hình).
Nối: salary_store.store (compute_month_payroll). Tests: tests/test_salary_bonus.py.
"""
from __future__ import annotations

THUONG_CHUYEN_CAN = 200_000        # đồng / tháng, cố định
THUONG_VE_SINH_MOI_NGAY = 12_000   # đồng / 1 ngày công


def bonus_amounts(cong: float, *, chuyen_can: bool, ve_sinh: bool) -> tuple[float, float]:
    """(thưởng chuyên cần, thưởng vệ sinh) của 1 thợ trong 1 tháng.

    Tắt = 0. Công âm/rỗng coi như 0 (không có chấm công thì thưởng vệ sinh = 0,
    KHÔNG phải lỗi)."""
    cc = float(THUONG_CHUYEN_CAN) if chuyen_can else 0.0
    days = max(0.0, float(cong or 0))
    vs = THUONG_VE_SINH_MOI_NGAY * days if ve_sinh else 0.0
    return cc, vs
