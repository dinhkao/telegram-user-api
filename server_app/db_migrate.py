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
_ORDERS_SPID_MARKER = "pid_orders_spid_backfilled"


def _backfill_return_items_sp_id(conn) -> None:
    """Gắn sp_id cho item phiếu TRẢ HÀNG cũ (tạo trước 2026-07-09). Vài row —
    quét mỗi boot, chỉ đụng phiếu còn item thiếu sp_id. Mã chết giữ nguyên."""
    from product_store import resolve_code
    rows = conn.execute(
        "SELECT DISTINCT r.id FROM return_slips r, json_each(r.items) je "
        "WHERE json_extract(je.value, '$.sp_id') IS NULL"
    ).fetchall()
    if not rows:
        return
    n = 0
    with transaction(conn):
        for (rid,) in rows:
            items = json.loads(conn.execute(
                "SELECT items FROM return_slips WHERE id = ?", (rid,)).fetchone()[0] or "[]")
            dirty = False
            for it in items:
                if isinstance(it, dict) and it.get("sp_id") is None:
                    prod = resolve_code(conn, it.get("sp"))
                    if prod:
                        it["sp_id"] = prod["id"]
                        dirty = True
            if dirty:
                conn.execute("UPDATE return_slips SET items = ? WHERE id = ?",
                             (json.dumps(items, ensure_ascii=False), rid))
                n += 1
    if n:
        log.info("backfill sp_id phiếu trả hàng: %d phiếu", n)


def _backfill_orders_sp_id(conn) -> None:
    """1 LẦN: gắn `sp_id` cho MỌI item hoá đơn trong 16k+ blob đơn lịch sử.

    Thời điểm vàng = TRƯỚC lần đổi mã đầu tiên (mã↔SP còn 1-1). Chỉ THÊM sp_id —
    `sp`/giá/tên snapshot giữ nguyên tại chỗ (không xoá dấu vết). Mã không resolve
    được (SP đã xoá khỏi danh mục) giữ nguyên không sp_id → hiển thị fallback.
    Batch 500 đơn/transaction; idempotent (marker + item đã có sp_id thì bỏ qua);
    chạy TRƯỚC khi server nhận request nên không đụng writer nào."""
    row = conn.execute("SELECT value FROM kv_store WHERE path = ?", (_ORDERS_SPID_MARKER,)).fetchone()
    if row and row[0]:
        return
    from product_store import resolve_code
    cache: dict[str, int | None] = {}

    def _rid(code) -> int | None:
        c = str(code or "").strip().upper()
        if not c:
            return None
        if c not in cache:
            p = resolve_code(conn, c)
            cache[c] = int(p["id"]) if p else None
        return cache[c]

    t0 = time.monotonic()
    last, scanned, changed, items_set, items_orphan = 0, 0, 0, 0, 0
    while True:
        # lặp theo rowid (KHÔNG theo thread_id — có row rác thread_id NULL sẽ bị sót)
        rows = conn.execute(
            "SELECT rowid, json FROM orders WHERE rowid > ? AND json IS NOT NULL "
            "ORDER BY rowid LIMIT 500",
            (last,),
        ).fetchall()
        if not rows:
            break
        with transaction(conn):
            for tid, jtext in rows:
                scanned += 1
                try:
                    j = json.loads(jtext)
                except Exception:
                    continue
                dirty = False
                for arr in ("invoice", "invoice_items"):
                    val = j.get(arr)
                    if not isinstance(val, list):  # blob hỏng legacy (int/dict) — bỏ qua
                        continue
                    for it in val:
                        if not isinstance(it, dict) or it.get("sp_id") is not None:
                            continue
                        pid = _rid(it.get("sp"))
                        if pid is not None:
                            it["sp_id"] = pid
                            items_set += 1
                            dirty = True
                        elif it.get("sp"):
                            items_orphan += 1
                if dirty:
                    # KHÔNG đụng updated_at — backfill không phải thao tác nghiệp vụ
                    conn.execute("UPDATE orders SET json = ? WHERE rowid = ?",
                                 (json.dumps(j, ensure_ascii=False), tid))
                    changed += 1
        last = rows[-1][0]
    conn.execute(
        "INSERT INTO kv_store (path, value, updated_at) VALUES (?, '1', ?) "
        "ON CONFLICT(path) DO UPDATE SET value = '1', updated_at = excluded.updated_at",
        (_ORDERS_SPID_MARKER, int(time.time() * 1000)),
    )
    conn.commit()
    log.info("backfill sp_id: %d/%d đơn cập nhật, %d item gắn id, %d item mã mồ côi, %.1fs",
             changed, scanned, items_set, items_orphan, time.monotonic() - t0)


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
    # can_produce_directly: SP có công thức = ĐÓNG GÓI (không SX trực tiếp) — giữ hành vi
    # cũ. Chạy 1 lần (marker) để không đè lựa chọn admin sau này.
    try:
        _m = "migrate/can_produce_directly_v1"
        if not conn.execute("SELECT value FROM kv_store WHERE path = ?", (_m,)).fetchone():
            conn.execute(
                "UPDATE products SET can_produce_directly = 0 WHERE id IN "
                "(SELECT DISTINCT product_id FROM product_recipes WHERE product_id IS NOT NULL AND ratio > 0)")
            conn.execute("INSERT INTO kv_store (path, value, updated_at) VALUES (?, '1', ?) "
                         "ON CONFLICT(path) DO NOTHING", (_m, int(time.time() * 1000)))
            conn.commit()
    except Exception:  # noqa: BLE001
        log.exception("backfill can_produce_directly thất bại (bỏ qua)")
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
    # đơn hàng: backfill sp_id toàn bộ blob lịch sử (1 lần; fail = hiển thị fallback mã)
    try:
        _backfill_orders_sp_id(conn)
    except Exception:  # noqa: BLE001 — thiếu sp_id chỉ mất tra-cứu-theo-id, không sai số
        log.exception("backfill sp_id thất bại — chạy lại ở boot sau")
    # phiếu trả hàng: item cũ thiếu sp_id (rẻ — vài row, WHERE lọc sẵn, chạy mỗi boot vô hại)
    try:
        _backfill_return_items_sp_id(conn)
    except Exception:  # noqa: BLE001
        log.exception("backfill sp_id phiếu trả thất bại (bỏ qua)")
    # price_history: cột product_id + backfill (nằm trong create_price_history_table)
    try:
        from price_list_store.history import create_price_history_table
        create_price_history_table(conn)
        conn.commit()
    except Exception:  # noqa: BLE001
        log.exception("migrate price_history product_id thất bại (bỏ qua)")
    log.info("boot migrations OK (products.id + history + inventory/recipe/production product_id + SP_INFO + price keys)")
