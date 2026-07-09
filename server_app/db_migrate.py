"""Migration app.db chạy lúc BOOT — bootstrap.main gọi TRƯỚC khi đăng ký handler
và mở web server, để không request nào chạy trên schema nửa vời. Mọi bước đều
idempotent (check cột/bảng/marker — chạy lại vô hại). Nối: product_store, order_db."""
from __future__ import annotations

import logging

from order_db import _get_connection
from product_store import create_products_table, migrate_products_table

log = logging.getLogger("server")


def run_boot_migrations() -> None:
    conn = _get_connection()
    # products: id INTEGER PK (danh tính bất biến) + bảng product_code_history
    create_products_table(conn)
    migrate_products_table(conn)
    # kho + công thức: cột product_id/ingredient_id + backfill theo mã (idempotent —
    # cũng chạy lazily trong inventory_routes._ensure, gọi ở đây cho chắc lúc boot)
    from inventory_store.schema import create_inventory_table, migrate_inventory_table
    from recipe_store.schema import create_recipe_table
    create_inventory_table(conn)
    migrate_inventory_table(conn)
    create_recipe_table(conn)
    log.info("boot migrations OK (products.id + code_history + inventory/recipe product_id)")
