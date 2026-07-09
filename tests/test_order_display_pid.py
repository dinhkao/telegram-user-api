"""Tests Phase 4 product-id cho đơn hàng: freeze gắn sp_id + chuẩn hoá mã,
parser nhận mã cũ, hiển thị resolve theo id (fallback snapshot), tra đơn-theo-SP
qua mã cũ/sp_id, backfill sp_id idempotent."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from order_store.display import invalidate_display_maps, resolve_invoice_display
from order_store.free_text import parse_invoice_free_text
from order_store.product_orders import count_orders_containing_product, orders_containing_product
from product_store import (
    create_products_table,
    freeze_invoice_cost_prices,
    get_product,
    migrate_products_table,
    record_code_change,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from server_app.db_migrate import _backfill_orders_sp_id
from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        invalidate_display_maps()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        self.conn.execute(
            "CREATE TABLE orders (thread_id INTEGER PRIMARY KEY, firebase_key TEXT, "
            "json TEXT, updated_at TEXT, deleted_at TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv_store (path TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
        self.conn.execute("CREATE TABLE customers (firebase_key TEXT PRIMARY KEY, json TEXT, deleted_at TEXT)")
        self.conn.commit()
        upsert_product(self.conn, "K10", name="Kẹo 10", cost_price=3000)
        self.pid = get_product(self.conn, "K10")["id"]

    def tearDown(self):
        self.conn.close()
        invalidate_display_maps()
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
        invalidate_display_maps()

    def _add_order(self, tid, items):
        self.conn.execute(
            "INSERT INTO orders (thread_id, firebase_key, json, updated_at) VALUES (?,?,?,datetime('now'))",
            (tid, f"fk{tid}", json.dumps({"text": f"đơn {tid}", "invoice": items}, ensure_ascii=False)))
        self.conn.commit()


class FreezeAndParse(Base):
    def test_freeze_adds_sp_id_and_normalizes_old_code(self):
        self._rename("K10", "K10X", self.pid)
        out = freeze_invoice_cost_prices(self.conn, [{"sp": "K10", "sl": 2, "price": 9000}])
        self.assertEqual(out[0]["sp"], "K10X")
        self.assertEqual(out[0]["sp_id"], self.pid)
        self.assertEqual(out[0]["cost_price"], 3000)
        self.assertTrue(out[0]["known"])

    def test_parser_accepts_old_code(self):
        self._rename("K10", "K10X", self.pid)
        inv = parse_invoice_free_text(self.conn, "k10 5 9000")
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["sp"], "K10X")   # chuẩn hoá ngay lúc parse
        self.assertEqual(inv[0]["sl"], 5)
        self.assertEqual(inv[0]["price"], 9000)


class Display(Base):
    def test_display_follows_rename_and_falls_back(self):
        items = [{"sp": "K10", "sp_id": self.pid, "sl": 1, "price": 100},
                 {"sp": "LẠHOẮC", "sl": 2, "price": 200}]
        self._rename("K10", "K10X", self.pid)
        disp = resolve_invoice_display(items, self.conn)
        self.assertEqual(disp[0]["sp"], "K10X")            # theo id
        self.assertEqual(disp[1]["sp"], "LẠHOẮC")          # mồ côi giữ snapshot
        self.assertEqual(items[0]["sp"], "K10")            # blob gốc không đổi
        # đơn cổ chưa backfill (chỉ có sp mã cũ) vẫn resolve qua alias
        disp2 = resolve_invoice_display([{"sp": "K10", "sl": 1, "price": 5}], self.conn)
        self.assertEqual(disp2[0]["sp"], "K10X")


class ProductOrders(Base):
    def test_orders_found_by_old_new_code_and_spid(self):
        self._add_order(1, [{"sp": "K10", "sl": 3, "price": 100}])                       # đơn cổ, chưa sp_id
        self._add_order(2, [{"sp": "K10", "sp_id": self.pid, "sl": 4, "price": 100}])    # đơn mới
        self._rename("K10", "K10X", self.pid)
        self._add_order(3, [{"sp": "K10X", "sp_id": self.pid, "sl": 5, "price": 100}])   # sau đổi mã
        for q in ("K10X", "K10", "k10x"):
            self.assertEqual(count_orders_containing_product(self.conn, q), 3, q)
        rows = orders_containing_product(self.conn, "K10X")
        self.assertEqual({r["thread_id"] for r in rows}, {1, 2, 3})


class Backfill(Base):
    def test_backfill_sets_ids_skips_orphans_idempotent(self):
        self._add_order(1, [{"sp": "K10", "sl": 3, "price": 100}])
        self._add_order(2, [{"sp": "MỒCÔI", "sl": 1, "price": 50}])
        _backfill_orders_sp_id(self.conn)
        j1 = json.loads(self.conn.execute("SELECT json FROM orders WHERE thread_id=1").fetchone()[0])
        j2 = json.loads(self.conn.execute("SELECT json FROM orders WHERE thread_id=2").fetchone()[0])
        self.assertEqual(j1["invoice"][0]["sp_id"], self.pid)
        self.assertEqual(j1["invoice"][0]["sp"], "K10")       # snapshot giữ nguyên
        self.assertNotIn("sp_id", j2["invoice"][0])            # mồ côi không bịa id
        _backfill_orders_sp_id(self.conn)                      # marker → no-op
        self.assertTrue(self.conn.execute(
            "SELECT value FROM kv_store WHERE path='pid_orders_spid_backfilled'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
