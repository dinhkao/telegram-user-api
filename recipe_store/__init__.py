"""recipe_store — công thức sản xuất (BOM): 1 sản phẩm cần các nguyên liệu (product
khác) theo tỉ lệ. Bảng product_recipes trong app.db. Dùng khi nhập thùng phiếu SX
để tự trừ kho nguyên liệu (inventory_store.fifo_consume). Nối: utils.db.
"""
from .schema import create_recipe_table
from .queries import list_recipe, set_recipe_line, delete_recipe_line, recipe_needs

__all__ = [
    "create_recipe_table",
    "list_recipe",
    "set_recipe_line",
    "delete_recipe_line",
    "recipe_needs",
]
