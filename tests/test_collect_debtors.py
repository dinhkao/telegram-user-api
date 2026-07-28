"""Tests cho danh sách khách nợ của trang Thu tiền hàng loạt (_load_debtors).

Bọc phần thuần-DB: gom số thu được theo khách + phần ĐƠN ĐÃ ẨN khỏi trang thu
tiền (cờ bypass_debt) khi client hỏi `?hidden=1`. Không chạm KiotViet/mạng.
"""
from __future__ import annotations

import json
import sqlite3
import time
import unittest

from server_app.order_api_collect import _load_debtors

_ORDERS_DDL = """
CREATE TABLE orders (
    firebase_key TEXT PRIMARY KEY,
    thread_id    INTEGER UNIQUE,
    channel_id   INTEGER,
    message_id   INTEGER,
    json         TEXT NOT NULL,
    updated_at   INTEGER NOT NULL,
    deleted_at   INTEGER
)
"""
_CUSTOMERS_DDL = """
CREATE TABLE customers (
    firebase_key TEXT PRIMARY KEY,
    json         TEXT NOT NULL,
    deleted_at   INTEGER
)
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(_ORDERS_DDL)
    conn.execute(_CUSTOMERS_DDL)
    return conn


def _put(conn, tid: int, data: dict, deleted: bool = False):
    conn.execute(
        "INSERT INTO orders (firebase_key, thread_id, channel_id, message_id, json, updated_at, deleted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"fk-{tid}", tid, 1, 1, json.dumps(data, ensure_ascii=False), int(time.time() * 1000),
         (int(time.time()) if deleted else None)),
    )


def _cust(conn, key: str, name: str, kh_id="kv-1", debt=None):
    conn.execute(
        "INSERT INTO customers (firebase_key, json, deleted_at) VALUES (?, ?, NULL)",
        (key, json.dumps({"name": name, "kh_id": kh_id, "debt": debt}, ensure_ascii=False)),
    )


def _order(cust="K1", created="2026-07-01T00:00:00", total=100, **extra):
    d = {"khach_hang_id": cust, "created": created, "invoice": [{"sp": "A", "price": total, "sl": 1}]}
    d.update(extra)
    return d


def _by_key(res: dict) -> dict:
    return {d["key"]: d for d in res["debtors"]}


class LoadDebtors(unittest.TestCase):
    def _fixture(self):
        conn = _conn()
        _cust(conn, "K1", "Khách Một")
        _cust(conn, "K2", "Khách Hai")
        _put(conn, 10, _order(created="2026-07-02T00:00:00", total=300))
        _put(conn, 11, _order(created="2026-07-01T00:00:00", total=100))
        _put(conn, 12, _order(created="2026-07-03T00:00:00", total=60, bypass_debt=True))   # ẩn
        # K2 chỉ còn đơn ẩn
        _put(conn, 20, _order(cust="K2", created="2026-07-04T00:00:00", total=500, bypass_debt=True))
        _put(conn, 21, _order(cust="K2", created="2026-07-05T00:00:00", total=70, bo_theo_doi_no=1))
        return conn

    def test_default_excludes_hidden_orders_and_hidden_only_customers(self):
        res = _load_debtors(self._fixture())
        self.assertEqual([d["key"] for d in res["debtors"]], ["K1"])
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["total_collectable"], 400)          # 300 + 100, KHÔNG cộng đơn ẩn
        d = _by_key(res)["K1"]
        self.assertEqual(d["order_count"], 2)
        self.assertEqual(d["source_thread_id"], 11)              # đơn cũ nhất còn thu được
        self.assertNotIn("hidden_orders", d)
        # Số tóm tắt đơn ẩn vẫn có sẵn để hiện nút "Xem đơn đã ẩn".
        self.assertEqual(res["hidden_count"], 2)
        self.assertEqual(res["hidden_total"], 560)
        self.assertEqual(res["hidden_customer_count"], 2)
        self.assertEqual(d["hidden_count"], 1)
        self.assertEqual(d["hidden_amount"], 60)

    def test_with_hidden_lists_hidden_orders_and_hidden_only_customer(self):
        res = _load_debtors(self._fixture(), True)
        self.assertEqual(sorted(d["key"] for d in res["debtors"]), ["K1", "K2"])
        # Tổng/đếm vẫn CHỈ tính phần thu được → số đầu trang không đổi.
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["total_collectable"], 400)
        k1, k2 = _by_key(res)["K1"], _by_key(res)["K2"]
        self.assertFalse(k1["hidden_only"])
        self.assertEqual([o["thread_id"] for o in k1["hidden_orders"]], [12])
        self.assertEqual(k1["hidden_orders"][0]["debt"], 60)
        self.assertTrue(k2["hidden_only"])
        self.assertEqual(k2["collectable"], 0)
        self.assertEqual(k2["order_count"], 0)
        self.assertEqual([o["thread_id"] for o in k2["hidden_orders"]], [20])   # bỏ theo dõi nợ không tính
        self.assertEqual(k2["source_thread_id"], 20)                            # link mở được trang thu tiền
        # Khách chỉ còn đơn ẩn xếp sau khách thu được.
        self.assertEqual([d["key"] for d in res["debtors"]], ["K1", "K2"])

    def test_partially_paid_hidden_order_uses_remaining(self):
        conn = _conn()
        _cust(conn, "K3", "Khách Ba")
        _put(conn, 30, _order(cust="K3", total=200, bypass_debt=True, payments=[{"amount": 80}]))
        res = _load_debtors(conn, True)
        d = _by_key(res)["K3"]
        self.assertEqual(d["hidden_amount"], 120)
        self.assertEqual(d["hidden_orders"][0]["debt"], 120)
        self.assertEqual(d["hidden_orders"][0]["total"], 200)


if __name__ == "__main__":
    unittest.main()
