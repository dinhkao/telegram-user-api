"""Migration app.db chạy lúc BOOT — bootstrap.main gọi TRƯỚC khi đăng ký handler
và mở web server, để không request nào chạy trên schema nửa vời. Mọi bước đều
idempotent (check cột/bảng/marker — chạy lại vô hại). Nối: product_store, order_db,
price_list_store (đổi key bảng giá mã→product_id, có verify)."""
from __future__ import annotations

import json
import logging
import time

from order_db import _get_connection
from product_store import create_products_table, migrate_products_table
from utils.db import transaction

log = logging.getLogger("server")

_PRICE_KEYS_MARKER = "pid_price_keys_migrated"


def _migrate_price_list_keys(conn) -> None:
    """1 LẦN: key bảng giá (chung + riêng 213 khách) mã → str(product_id).

    An toàn: chạy trong 1 transaction; TỪNG bảng/khách verify map hiệu lực
    (mã hiện hành → giá) TRƯỚC == SAU — lệch 1 đồng là raise → rollback toàn bộ,
    giữ format cũ (reader hiểu cả 2 format qua isdigit nên hệ vẫn chạy đúng)."""
    row = conn.execute("SELECT value FROM kv_store WHERE path = ?", (_PRICE_KEYS_MARKER,)).fetchone()
    if row and row[0]:
        return
    from price_list_store.keys import effective_code_prices, migrate_price_keys
    n_lists = n_cust = 0
    with transaction(conn):
        r = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'").fetchone()
        if r and r[0]:
            blob = json.loads(r[0])
            for lid, v in blob.items():
                raw = (v or {}).get("price_list") or {}
                if not raw:
                    continue
                before = effective_code_prices(conn, raw, aliases=False)
                new_raw = migrate_price_keys(conn, raw)
                after = effective_code_prices(conn, new_raw, aliases=False)
                if before != after:
                    raise RuntimeError(f"bảng giá {lid}: verify lệch — bỏ migration")
                v["price_list"] = new_raw
                n_lists += 1
            conn.execute(
                "UPDATE kv_store SET value = ?, updated_at = ? WHERE path = 'bang_gia_moi'",
                (json.dumps(blob, ensure_ascii=False), int(time.time() * 1000)),
            )
        for fk, jtext in conn.execute(
            "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL "
            "AND json_extract(json, '$.personal_price_list') IS NOT NULL"
        ).fetchall():
            cust = json.loads(jtext)
            raw = cust.get("personal_price_list")
            if not isinstance(raw, dict) or not raw:
                continue
            before = effective_code_prices(conn, raw, aliases=False)
            new_raw = migrate_price_keys(conn, raw)
            after = effective_code_prices(conn, new_raw, aliases=False)
            if before != after:
                raise RuntimeError(f"bảng giá riêng khách {fk}: verify lệch — bỏ migration")
            cust["personal_price_list"] = new_raw
            conn.execute(
                "UPDATE customers SET json = ? WHERE firebase_key = ?",
                (json.dumps(cust, ensure_ascii=False), fk),
            )
            n_cust += 1
        conn.execute(
            "INSERT INTO kv_store (path, value, updated_at) VALUES (?, '1', ?) "
            "ON CONFLICT(path) DO UPDATE SET value = '1', updated_at = excluded.updated_at",
            (_PRICE_KEYS_MARKER, int(time.time() * 1000)),
        )
    log.info("price keys -> product_id: %d bảng chung + %d khách (verify diff=0)", n_lists, n_cust)


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
    # bảng giá: key mã → product_id (1 lần, verify từng bảng/khách, fail = giữ nguyên)
    try:
        _migrate_price_list_keys(conn)
    except Exception:  # noqa: BLE001 — reader hiểu cả 2 format, không chặn boot
        log.exception("migrate price keys thất bại — GIỮ format cũ, hệ vẫn chạy")
    log.info("boot migrations OK (products.id + history + inventory/recipe/production product_id + SP_INFO + price keys)")
