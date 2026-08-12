"""Giá mặc định khi parse hoá đơn = GIÁ KHÁCH ĐÃ MUA LẦN GẦN NHẤT.

Khoá hành vi của `order_store.last_prices` + 2 parser dùng nó: đơn mới nhất
thắng đơn cũ, bảng giá chỉ là dự phòng, giá gõ tay vẫn thắng tất cả, và mã SP đã
đổi tên vẫn khớp (đơn cũ ghi mã cũ → key trả về là mã hiện hành).
"""
from __future__ import annotations

import json
import sqlite3
import time
import unittest

from order_store.comma_parser import parse_comma_text
from order_store.free_text import parse_invoice_free_text
from order_store.last_prices import invalidate_last_price_cache, last_order_prices
from product_store.schema import create_products_table, _invalidate_products_cache

_ORDERS_DDL = """
CREATE TABLE orders (
    firebase_key  TEXT PRIMARY KEY,
    thread_id     INTEGER UNIQUE,
    channel_id    INTEGER,
    message_id    INTEGER,
    json          TEXT NOT NULL,
    updated_at    INTEGER NOT NULL,
    deleted_at    INTEGER,
    order_created TEXT
)
"""

KH = "77"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(_ORDERS_DDL)
    conn.execute("CREATE TABLE customers (firebase_key TEXT PRIMARY KEY, json TEXT, deleted_at INTEGER)")
    conn.execute("CREATE TABLE kv_store (path TEXT PRIMARY KEY, value TEXT)")
    create_products_table(conn)   # kèm product_code_history
    return conn


def _add_order(conn, thread_id: int, created: str, items: list[dict], *, kh=KH, deleted=None):
    data = {"khach_hang_id": kh, "created": created, "invoice": items}
    conn.execute(
        "INSERT INTO orders(firebase_key, thread_id, channel_id, message_id, json, updated_at, deleted_at, order_created)"
        " VALUES (?, ?, 1, 1, ?, ?, ?, ?)",
        (f"fk-{thread_id}", thread_id, json.dumps(data, ensure_ascii=False), int(time.time() * 1000), deleted, created),
    )


def _item(sp, price, *, sp_id=None):
    it = {"sp": sp, "sl": 10, "price": price}
    if sp_id is not None:
        it["sp_id"] = sp_id
    return it


class LastOrderPrices(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        _invalidate_products_cache()
        invalidate_last_price_cache()
        self.conn.execute("INSERT INTO products(id, code, name) VALUES (1, 'SP1', 'SP một')")
        self.conn.execute("INSERT INTO products(id, code, name) VALUES (2, 'SP2', 'SP hai')")
        self.conn.execute(
            "INSERT INTO customers(firebase_key, json) VALUES (?, ?)",
            (KH, json.dumps({"name": "Khách A", "personal_price_list": {"SP1": 20000, "SP2": 30000}})),
        )

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        invalidate_last_price_cache()

    def test_newest_order_wins(self):
        _add_order(self.conn, 1, "2026-08-01T00:00:00.000Z", [_item("SP1", 15000)])
        _add_order(self.conn, 2, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        self.assertEqual(last_order_prices(self.conn, KH), {"SP1": 16000})

    def test_falls_back_to_older_order_per_product(self):
        _add_order(self.conn, 1, "2026-08-01T00:00:00.000Z", [_item("SP1", 15000), _item("SP2", 25000)])
        _add_order(self.conn, 2, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        self.assertEqual(last_order_prices(self.conn, KH), {"SP1": 16000, "SP2": 25000})

    def test_ignores_other_customers_deleted_orders_and_zero_price(self):
        _add_order(self.conn, 1, "2026-08-05T00:00:00.000Z", [_item("SP1", 99000)], kh="99")
        _add_order(self.conn, 2, "2026-08-04T00:00:00.000Z", [_item("SP1", 88000)], deleted=1)
        _add_order(self.conn, 3, "2026-08-03T00:00:00.000Z", [_item("SP1", 0), _item("SP2", 25000)])
        self.assertEqual(last_order_prices(self.conn, KH), {"SP2": 25000})

    def test_renamed_product_matches_by_id_and_old_code(self):
        # Đơn cũ ghi mã cũ 'SPX' (theo id) → key trả về là mã HIỆN HÀNH 'SP1'
        self.conn.execute(
            "INSERT INTO product_code_history(product_id, old_code, new_code, changed_at)"
            " VALUES (1, 'SPX', 'SP1', '2026-08-01T00:00:00.000Z')"
        )
        _add_order(self.conn, 1, "2026-08-05T00:00:00.000Z", [_item("SPX", 17000, sp_id=1)])
        self.assertEqual(last_order_prices(self.conn, KH), {"SP1": 17000})
        invalidate_last_price_cache()
        _invalidate_products_cache()
        self.conn.execute("DELETE FROM orders")
        _add_order(self.conn, 2, "2026-08-05T00:00:00.000Z", [_item("SPX", 17500)])   # không có sp_id
        self.assertEqual(last_order_prices(self.conn, KH), {"SP1": 17500})


class ParsersUseLastPrice(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        _invalidate_products_cache()
        invalidate_last_price_cache()
        self.conn.execute("INSERT INTO products(id, code, name) VALUES (1, 'SP1', 'SP một')")
        self.conn.execute(
            "INSERT INTO customers(firebase_key, json) VALUES (?, ?)",
            (KH, json.dumps({"name": "Khách A", "personal_price_list": {"SP1": 20000}})),
        )

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        invalidate_last_price_cache()

    def test_free_text_prefers_last_order_price(self):
        _add_order(self.conn, 1, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        out = parse_invoice_free_text(self.conn, "SP1 10", KH)
        self.assertEqual([it["price"] for it in out], [16000])

    def test_free_text_falls_back_to_price_list(self):
        out = parse_invoice_free_text(self.conn, "SP1 10", KH)      # khách chưa mua bao giờ
        self.assertEqual([it["price"] for it in out], [20000])

    def test_typed_price_still_wins(self):
        _add_order(self.conn, 1, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        out = parse_invoice_free_text(self.conn, "SP1 10 12000", KH)
        self.assertEqual([it["price"] for it in out], [12000])

    def test_comma_parser_prefers_last_order_price(self):
        _add_order(self.conn, 1, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        out = parse_comma_text("SP1 10", self.conn, KH)
        self.assertEqual([it["price"] for it in out], [16000])
        invalidate_last_price_cache()
        self.assertEqual([it["price"] for it in parse_comma_text("SP1  10  12000", self.conn, KH)], [12000])


class LastPricesCustKeyColumn(unittest.TestCase):
    """Đường CÓ cột generated `cust_key` (+ idx_orders_cust_created) phải cho ĐÚNG
    kết quả như đường dự phòng dùng thẳng biểu thức json_extract.

    Bảng thật (app.db) có cột đó do `server_app.orders_db.ensure_orders_stats_columns`
    thêm; bảng test ở lớp trên thì không → 2 lớp này phủ cả 2 nhánh.
    """

    def setUp(self):
        invalidate_last_price_cache()
        _invalidate_products_cache()
        self.conn = _conn()
        self.conn.execute(
            "ALTER TABLE orders ADD COLUMN cust_key GENERATED ALWAYS AS ("
            " coalesce(json_extract(json, '$.khach_hang_id'), json_extract(json, '$.khID'))) VIRTUAL"
        )
        self.conn.execute(
            "CREATE INDEX idx_orders_cust_created ON orders(cust_key, order_created DESC, thread_id DESC)"
            " WHERE deleted_at IS NULL"
        )

    def tearDown(self):
        self.conn.close()
        invalidate_last_price_cache()

    def test_uses_index_and_matches_expression_path(self):
        from order_store.last_prices import _SQL_BY_COL, _SQL_BY_EXPR
        _add_order(self.conn, 1, "2026-08-01T00:00:00.000Z", [_item("SP1", 19000)])
        _add_order(self.conn, 2, "2026-08-05T00:00:00.000Z", [_item("SP1", 16000)])
        _add_order(self.conn, 3, "2026-08-06T00:00:00.000Z", [_item("SP1", 99000)], deleted=1)
        _add_order(self.conn, 4, "2026-08-06T00:00:00.000Z", [_item("SP1", 88000)], kh="99")

        plan = self.conn.execute("EXPLAIN QUERY PLAN " + _SQL_BY_COL, (KH, 30)).fetchall()
        self.assertIn("idx_orders_cust_created", " ".join(r[3] for r in plan))
        for key in (KH, "99", "khach-chua-mua-bao-gio"):
            self.assertEqual(
                [r[0] for r in self.conn.execute(_SQL_BY_COL, (key, 30)).fetchall()],
                [r[0] for r in self.conn.execute(_SQL_BY_EXPR, (key, 30)).fetchall()],
                f"2 đường query lệch nhau ở khách {key!r}",
            )
        self.assertEqual(last_order_prices(self.conn, KH), {"SP1": 16000})   # đơn mới thắng, bỏ đơn đã xoá


if __name__ == "__main__":
    unittest.main()
