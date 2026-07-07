"""Product store + profit calc (schema, queries, freeze cost prices) -> shared SQLite. Root shim: product_db.py."""
from .schema import create_products_table, migrate_products_table
from .queries import get_product, get_all_products, upsert_product, delete_product, bulk_update_cost_prices, set_kiotviet_link, clear_kiotviet_link, set_material
from .profit import calculate_order_profit, freeze_invoice_cost_prices, get_products_from_orders

__all__ = [
    "create_products_table",
    "migrate_products_table",
    "get_product",
    "get_all_products",
    "upsert_product",
    "delete_product",
    "bulk_update_cost_prices",
    "set_kiotviet_link",
    "clear_kiotviet_link",
    "set_material",
    "calculate_order_profit",
    "freeze_invoice_cost_prices",
    "get_products_from_orders",
]
