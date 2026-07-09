"""recipe_store — công thức sản xuất (BOM): 1 sản phẩm cần các nguyên liệu (product
khác) theo tỉ lệ. Bảng product_recipes trong app.db. Nhu cầu NL theo LOẠI PHIẾU:
sản xuất = không cần, đóng gói = bắt buộc đủ MỌI NL (trừ kho qua
inventory_store.allocate_picks kind='production'). Nối: utils.db.
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
