"""bean_store — KHO ĐẬU: hệ kho RIÊNG, tách hẳn kho hàng hoá (inventory_store).

4 bảng trong app.db: `bean_places` (kho A/B…), `beans` (danh mục đậu),
`bean_slips` + `bean_moves` (phiếu nhập/xuất/điều chỉnh và dòng biến động).
KHÔNG có bảng tồn — tồn = Σ delta của các phiếu còn sống (bean_store.stock), nên
xoá phiếu là tồn tự đúng. Luật thuần (dấu theo loại phiếu, ghép bảng tồn) ở
domain.py (unit-tested). DDL ensure per-module (schema.py, gọi từ route).
Dùng bởi server_app/bean_routes.py + bean_slip_routes.py.
"""
from .catalog import (add_bean, add_place, get_bean, get_place, list_beans, list_places,
                      soft_delete_bean, soft_delete_place, update_bean, update_place)
from .schema import ensure_tables
from .slips import create_slip, get_slip, list_slips, soft_delete_slip
from .stock import stock_by_bean, stock_cells, stock_of

__all__ = [
    "ensure_tables",
    "add_bean", "get_bean", "list_beans", "update_bean", "soft_delete_bean",
    "add_place", "get_place", "list_places", "update_place", "soft_delete_place",
    "create_slip", "get_slip", "list_slips", "soft_delete_slip",
    "stock_cells", "stock_of", "stock_by_bean",
]
