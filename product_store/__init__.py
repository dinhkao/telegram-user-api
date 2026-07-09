"""Product store + profit calc (schema, queries, resolve id↔code, freeze cost prices) -> shared SQLite. Root shim: product_db.py."""
from .schema import create_products_table, migrate_products_table
from .queries import get_product, get_product_by_id, get_all_products, upsert_product, delete_product, bulk_update_cost_prices, set_kiotviet_link, clear_kiotviet_link, set_material
from .resolve import resolve_code, resolve_code_to_id, code_alias_map, old_codes_of, record_code_change, kv_ids_for_items
from .rename import rename_product
from .profit import calculate_order_profit, freeze_invoice_cost_prices, get_products_from_orders

__all__ = [
    "rename_product",
    "create_products_table",
    "migrate_products_table",
    "get_product",
    "get_product_by_id",
    "get_all_products",
    "upsert_product",
    "delete_product",
    "bulk_update_cost_prices",
    "set_kiotviet_link",
    "clear_kiotviet_link",
    "set_material",
    "resolve_code",
    "resolve_code_to_id",
    "code_alias_map",
    "old_codes_of",
    "record_code_change",
    "kv_ids_for_items",
    "calculate_order_profit",
    "freeze_invoice_cost_prices",
    "get_products_from_orders",
]
