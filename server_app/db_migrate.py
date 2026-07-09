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
    # sản xuất: product_id trên slip + report_rows (backfill theo sp_name/mã)
    from production_store.schema import create_production_table, migrate_production_table
    from production_store.report_rows import ensure_report_rows_schema
    create_production_table(conn)
    migrate_production_table(conn)
    ensure_report_rows_schema(conn)
    # port SP_INFO (mâm/lượng mặc định) vào products — chỉ điền chỗ còn trống
    try:
        from bot_core.config import SP_INFO
        for code, info in SP_INFO.items():
            conn.execute(
                "UPDATE products SET prod_mam = COALESCE(prod_mam, ?), prod_luong = COALESCE(prod_luong, ?) "
                "WHERE code = ?",
                (info.get("mam"), info.get("luong"), str(code).upper()),
            )
        conn.commit()
    except Exception:  # noqa: BLE001 — SP_INFO legacy, thiếu cũng không chặn boot
        log.exception("seed SP_INFO -> products thất bại (bỏ qua)")
    log.info("boot migrations OK (products.id + history + inventory/recipe/production product_id + SP_INFO)")
