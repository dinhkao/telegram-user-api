"""Sổ GHI ĐỊNH MỨC nguyên liệu phụ khi sản xuất — KHÔNG trừ kho.

Mô hình: khi SX tạo thùng thành phẩm có công thức NL phụ (aux=1), TỰ GHI 1 bản ghi
"đã dùng amount = số cây × tỉ lệ" cho từng (thùng thành phẩm × NL phụ). Bản ghi này
CHỈ để theo dõi/đối chiếu — KHÔNG tạo box_allocations, KHÔNG giảm tồn kho. Cuối ngày
kiểm kho đối chiếu số ghi này với thực đếm rồi mới quyết định trừ (áp điều chỉnh).

Xóa thùng thành phẩm → VOID bản ghi (giữ dấu vết). Bảng `aux_usage_ledger` (app.db).
Nối: recipe_store (list_recipe aux=True), product_store (resolve), utils.db.
"""
from .store import (
    create_aux_usage_table,
    record_boxes_aux_usage,
    void_box_aux_usage,
    aux_usage_by_ingredient,
)

__all__ = [
    "create_aux_usage_table",
    "record_boxes_aux_usage",
    "void_box_aux_usage",
    "aux_usage_by_ingredient",
]
