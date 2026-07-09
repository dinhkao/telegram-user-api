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
    log.info("boot migrations OK (products.id + product_code_history)")
