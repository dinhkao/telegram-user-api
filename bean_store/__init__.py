"""bean_store — KHO ĐẬU: hệ kho RIÊNG, tách hẳn kho hàng hoá (inventory_store).

7 bảng trong app.db: `bean_places` (kho A/B…), `beans` (danh mục đậu),
`bean_units` (đơn vị quy đổi của từng loại đậu), `bean_slips` + `bean_moves`
(phiếu nhập/xuất/điều chỉnh và dòng biến động), `bean_stocktakes` +
`bean_stocktake_items` (phiếu KIỂM KHO — bean_store.stocktakes: chụp sổ, ghi số
đếm, chốt → sinh phiếu điều chỉnh). KHÔNG có bảng tồn — tồn = Σ delta
của các phiếu còn sống (bean_store.stock), nên xoá phiếu là tồn tự đúng. Mọi số
trong DB theo ĐƠN VỊ GỐC (`beans.unit`); đơn vị chọn lúc nhập/xuất chỉ là cách gõ,
được quy đổi ngay + lưu snapshot (bean_store.units). Luật thuần (dấu theo loại
phiếu, ghép bảng tồn) ở domain.py (unit-tested). DDL ensure per-module (schema.py,
gọi từ route). Dùng bởi server_app/bean_routes.py + bean_slip_routes.py +
bean_unit_routes.py + bean_stocktake_routes.py.
"""
from .catalog import (add_bean, add_place, get_bean, get_place, list_beans, list_places,
                      soft_delete_bean, soft_delete_place, update_bean, update_place)
from .schema import ensure_tables
from .slips import create_slip, get_slip, list_slips, soft_delete_slip
from .stock import stock_by_bean, stock_cells, stock_of
from .stocktakes import (complete_stocktake, create_stocktake, get_stocktake, list_stocktakes,
                         resync_stocktake, set_counts, void_stocktake)
from .units import (add_unit, delete_unit, get_unit, list_units, resolve_unit,
                    set_base_unit, units_by_bean, update_unit)

__all__ = [
    "ensure_tables",
    "add_bean", "get_bean", "list_beans", "update_bean", "soft_delete_bean",
    "add_place", "get_place", "list_places", "update_place", "soft_delete_place",
    "create_slip", "get_slip", "list_slips", "soft_delete_slip",
    "stock_cells", "stock_of", "stock_by_bean",
    "create_stocktake", "get_stocktake", "list_stocktakes", "set_counts", "resync_stocktake",
    "complete_stocktake", "void_stocktake",
    "list_units", "units_by_bean", "get_unit", "add_unit", "update_unit",
    "delete_unit", "resolve_unit", "set_base_unit",
]
