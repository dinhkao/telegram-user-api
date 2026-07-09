"""Tests Phase 0 product-id: migration rebuild (code PK → id PK, data giữ nguyên,
idempotent), resolver mã hiện-hành/mã-cũ qua product_code_history (luật hiện tại
thắng khi mã tái dùng), alias map cho parser, upsert giữ nguyên id."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import (
    code_alias_map,
    create_products_table,
    get_all_products,
    get_product,
    get_product_by_id,
    migrate_products_table,
    record_code_change,
    resolve_code,
    resolve_code_to_id,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass


class FreshSchema(Base):
    def test_create_has_id_and_upsert_assigns(self):
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        upsert_product(self.conn, "k10", name="Kẹo 10")
        p = get_product(self.conn, "K10")
        self.assertIsInstance(p["id"], int)
        self.assertEqual(get_product_by_id(self.conn, p["id"])["code"], "K10")

    def test_upsert_existing_keeps_id(self):
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        upsert_product(self.conn, "K10", name="A")
        pid = get_product(self.conn, "K10")["id"]
        upsert_product(self.conn, "K10", name="B", cost_price=123)
        p = get_product(self.conn, "K10")
        self.assertEqual(p["id"], pid)
        self.assertEqual(p["name"], "B")
        self.assertEqual(p["cost_price"], 123)


class OldShapeMigration(Base):
    def _make_old_table(self):
        # Bảng đời cũ: code TEXT PRIMARY KEY, THIẾU unit/is_material
        self.conn.execute(
            "CREATE TABLE products (code TEXT PRIMARY KEY, name TEXT, "
            "cost_price INTEGER DEFAULT 0, note TEXT, kv_id INTEGER, "
            "kv_full_name TEXT, kv_synced_at TEXT, created_at TEXT, updated_at TEXT)"
        )
        self.conn.execute(
            "INSERT INTO products (code, name, cost_price, kv_id) "
            "VALUES ('K2L', 'Kẹo 2L', 5000, 427881)"
        )
        self.conn.execute("INSERT INTO products (code, name) VALUES ('DM50', 'Đậu 50')")
        self.conn.commit()

    def test_rebuild_assigns_ids_keeps_data(self):
        self._make_old_table()
        migrate_products_table(self.conn)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(products)").fetchall()}
        self.assertIn("id", cols)
        p = get_product(self.conn, "K2L")
        self.assertEqual(p["kv_id"], 427881)
        self.assertEqual(p["cost_price"], 5000)
        self.assertEqual(p["unit"], "cây")  # cột thêm sau rebuild có default
        self.assertEqual(len(get_all_products(self.conn, _use_cache=False)), 2)
        with self.assertRaises(Exception):  # UNIQUE code vẫn ép
            self.conn.execute("INSERT INTO products (code) VALUES ('K2L')")

    def test_migrate_idempotent(self):
        self._make_old_table()
        migrate_products_table(self.conn)
        id1 = get_product(self.conn, "K2L")["id"]
        migrate_products_table(self.conn)
        self.assertEqual(get_product(self.conn, "K2L")["id"], id1)


class Resolver(Base):
    def setUp(self):
        super().setUp()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        upsert_product(self.conn, "K10", name="Kẹo 10")
        self.pid = get_product(self.conn, "K10")["id"]

    def _rename(self, old, new, pid):
        self.conn.execute("UPDATE products SET code = ? WHERE id = ?", (new, pid))
        record_code_change(self.conn, pid, old, new)
        self.conn.commit()
        _invalidate_products_cache()

    def test_resolve_current_and_old(self):
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(resolve_code(self.conn, "K10X")["id"], self.pid)
        self.assertEqual(resolve_code(self.conn, "k10")["id"], self.pid)  # mã cũ, chữ thường
        self.assertIsNone(resolve_code(self.conn, "ZZZ"))

    def test_reused_code_current_wins(self):
        self._rename("K10", "K10X", self.pid)
        upsert_product(self.conn, "K10", name="SP mới chiếm mã cũ")
        new_id = get_product(self.conn, "K10")["id"]
        self.assertNotEqual(new_id, self.pid)
        self.assertEqual(resolve_code(self.conn, "K10")["id"], new_id)  # hiện tại thắng
        self.assertNotIn("K10", code_alias_map(self.conn))

    def test_alias_map_and_chained_rename(self):
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(code_alias_map(self.conn)["K10"], self.pid)
        self.assertEqual(resolve_code_to_id(self.conn, "K10"), self.pid)
        # đổi tiếp K10X → K10Y: cả 2 mã cũ đều resolve về cùng SP
        self._rename("K10X", "K10Y", self.pid)
        self.assertEqual(resolve_code_to_id(self.conn, "K10"), self.pid)
        self.assertEqual(resolve_code_to_id(self.conn, "K10X"), self.pid)


if __name__ == "__main__":
    unittest.main()
