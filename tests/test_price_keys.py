"""Tests Phase 3 product-id cho bảng giá: key lưu = product_id (đổi mã không vỡ
giá), dịch về mã hiện hành khi đọc, alias mã cũ cho parser, migration key mã→id
verify diff=0, bảng giá hiệu lực của khách (chung + riêng đè)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from order_store.search import get_customer_price_list, get_customer_price_source
from price_list_store.keys import effective_code_prices, migrate_price_keys, to_pid_key
from product_store import (
    create_products_table,
    get_product,
    migrate_products_table,
    record_code_change,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from server_app.db_migrate import _migrate_price_list_keys
from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        self.conn.execute("CREATE TABLE customers (firebase_key TEXT PRIMARY KEY, json TEXT, deleted_at TEXT)")
        self.conn.execute("CREATE TABLE kv_store (path TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
        self.conn.commit()
        upsert_product(self.conn, "K10", name="Kẹo 10")
        self.pid = get_product(self.conn, "K10")["id"]

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def _rename(self, old, new, pid):
        self.conn.execute("UPDATE products SET code = ? WHERE id = ?", (new, pid))
        record_code_change(self.conn, pid, old, new)
        self.conn.commit()
        _invalidate_products_cache()

    def _seed_lists(self, shared: dict, personal: dict | None = None, cust_key="c1"):
        blob = {"1": {"name": "BG Sỉ", "price_list": shared}}
        self.conn.execute(
            "INSERT OR REPLACE INTO kv_store (path, value, updated_at) VALUES ('bang_gia_moi', ?, 0)",
            (json.dumps(blob, ensure_ascii=False),))
        cust = {"name": "Khách 1", "price_list": "1"}
        if personal:
            cust["personal_price_list"] = personal
        self.conn.execute(
            "INSERT OR REPLACE INTO customers (firebase_key, json) VALUES (?, ?)",
            (cust_key, json.dumps(cust, ensure_ascii=False)))
        self.conn.commit()


class Keys(Base):
    def test_to_pid_key(self):
        self.assertEqual(to_pid_key(self.conn, "K10"), str(self.pid))
        self.assertEqual(to_pid_key(self.conn, "k10"), str(self.pid))
        self.assertEqual(to_pid_key(self.conn, "LẠ123"), "LẠ123")      # legacy giữ nguyên
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(to_pid_key(self.conn, "K10"), str(self.pid))  # mã cũ → cùng pid

    def test_effective_prices_follow_rename_with_alias(self):
        raw = {str(self.pid): 5000, "KDDT480": 3000}
        self.assertEqual(effective_code_prices(self.conn, raw),
                         {"K10": 5000, "KDDT480": 3000})
        self._rename("K10", "K10X", self.pid)
        eff = effective_code_prices(self.conn, raw)
        self.assertEqual(eff["K10X"], 5000)        # mã hiện hành
        self.assertEqual(eff["K10"], 5000)         # alias mã cũ cho parser
        self.assertEqual(eff["KDDT480"], 3000)     # legacy passthrough
        # không alias khi tắt
        self.assertNotIn("K10", effective_code_prices(self.conn, raw, aliases=False))

    def test_deleted_product_price_dropped_reused_code_current_wins(self):
        raw = {str(self.pid): 5000}
        self._rename("K10", "K10X", self.pid)
        upsert_product(self.conn, "K10", name="SP mới chiếm mã")   # mã cũ tái dùng
        new_pid = get_product(self.conn, "K10")["id"]
        eff = effective_code_prices(self.conn, {**raw, str(new_pid): 7000})
        self.assertEqual(eff, {"K10X": 5000, "K10": 7000})         # alias không đè mã hiện hành
        self.conn.execute("DELETE FROM products WHERE id = ?", (new_pid,))
        self.conn.commit(); _invalidate_products_cache()
        eff2 = effective_code_prices(self.conn, {str(new_pid): 7000})
        self.assertEqual(eff2, {})                                  # SP xoá → giá ẩn


class MigrationAndCustomer(Base):
    def test_migrate_then_customer_effective_unchanged(self):
        self._seed_lists({"K10": 5000, "KDDT480": 3000}, personal={"K10": 4800})
        before = get_customer_price_list(self.conn, "c1")
        _migrate_price_list_keys(self.conn)
        blob = json.loads(self.conn.execute(
            "SELECT value FROM kv_store WHERE path='bang_gia_moi'").fetchone()[0])
        self.assertEqual(blob["1"]["price_list"], {str(self.pid): 5000, "KDDT480": 3000})
        after = get_customer_price_list(self.conn, "c1")
        self.assertEqual(before, after)                             # verify diff=0
        self.assertEqual(after["K10"], 4800)                        # riêng đè chung
        # marker → chạy lại no-op
        _migrate_price_list_keys(self.conn)

    def test_rename_after_migration_keeps_prices(self):
        self._seed_lists({"K10": 5000}, personal={"K10": 4800})
        _migrate_price_list_keys(self.conn)
        self._rename("K10", "K10X", self.pid)
        pl = get_customer_price_list(self.conn, "c1")
        self.assertEqual(pl["K10X"], 4800)                          # giá theo SP, không theo mã
        self.assertEqual(pl["K10"], 4800)                           # gõ mã cũ vẫn ăn giá
        price, source, name = get_customer_price_source(self.conn, "c1", "K10")
        self.assertEqual((price, source), (4800, "personal"))


if __name__ == "__main__":
    unittest.main()
