"""Store/context-level tests cho thu tiền GỘP (bulk payment) — temp SQLite, no KV.

Bọc phần TÍNH ĐƯỢC không cần mạng: lọc đơn đang nợ của khách
(_load_customer_debt_orders) + xoá cả 1 giao dịch gộp khỏi blob các đơn
(remove_batch_payments / find_batch_thread_ids). Lõi orchestration (KiotViet +
firebase) không test ở đây — cùng ranh giới với _process_payment_core.
"""
from __future__ import annotations

import json
import sqlite3
import time
import unittest

from api_helpers.payment_core import find_batch_thread_ids, remove_batch_payments
from server_app.customer_feed import _order_total_num
from server_app.order_api_bulk_payment import _load_customer_debt_orders

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


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(_ORDERS_DDL)
    return conn


def _put(conn, tid: int, data: dict, deleted: bool = False):
    conn.execute(
        "INSERT INTO orders (firebase_key, thread_id, channel_id, message_id, json, updated_at, deleted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"fk-{tid}", tid, 1, 1, json.dumps(data, ensure_ascii=False), int(time.time() * 1000),
         (int(time.time()) if deleted else None)),
    )


def _order(cust="K1", created="2026-07-01T00:00:00", total=100, **extra):
    d = {"khach_hang_id": cust, "created": created, "invoice": [{"sp": "A", "price": total, "sl": 1}]}
    d.update(extra)
    return d


class LoadCustomerDebtOrders(unittest.TestCase):
    def test_total_includes_fees_discount_but_excludes_old_debt(self):
        order = _order(
            total=1_000_000,
            pvc=30_000,
            vat=80_000,
            discount=50_000,
            hoadon={"print_content": {
                "tongtienhang": "1,000,000",
                "no_truoc": "9,000,000",
                "tongthanhtoan": "10,060,000",
            }},
        )
        self.assertEqual(_order_total_num(order), 1_060_000)

    def test_legacy_total_uses_printed_goods_not_total_with_old_debt(self):
        order = {
            "pvc": 30_000,
            "discount": 10_000,
            "hoadon": {"print_content": {
                "tongtienhang": "650.000",
                "no_truoc": "5.000.000",
                "tongthanhtoan": "5.670.000",
            }},
        }
        self.assertEqual(_order_total_num(order), 670_000)

    def test_only_unpaid_same_customer_sorted_old_first(self):
        conn = _conn()
        _put(conn, 10, _order(created="2026-07-03T00:00:00", total=300))   # mới hơn
        _put(conn, 11, _order(created="2026-07-01T00:00:00", total=100))   # cũ nhất
        _put(conn, 12, _order(created="2026-07-02T00:00:00", total=200))
        _put(conn, 20, _order(cust="K2", total=999))                       # khách khác
        _put(conn, 13, _order(created="2026-07-04T00:00:00", total=50,
                              payments=[{"amount": 10, "id": "p1"}]))       # thanh toán một phần
        _put(conn, 18, _order(created="2026-07-04T12:00:00", total=50,
                              payments=[{"amount": 20}, {"amount": 30}]))    # đã thanh toán đủ
        _put(conn, 14, _order(created="2026-07-05T00:00:00", total=50, bo_theo_doi_no=1))  # bỏ theo dõi
        _put(conn, 17, _order(created="2026-07-05T12:00:00", total=60, bypass_debt=True))   # chỉ ẩn khỏi thu tiền
        _put(conn, 15, _order(created="2026-07-06T00:00:00", total=0))     # tổng 0
        _put(conn, 16, _order(created="2026-07-07T00:00:00", total=70), deleted=True)      # đã xoá

        active, hidden = _load_customer_debt_orders(conn, "K1")
        self.assertEqual([o["thread_id"] for o in active], [11, 12, 10, 13])  # cũ → mới
        self.assertEqual([o["debt"] for o in active], [100, 200, 300, 40])
        self.assertEqual([o["thread_id"] for o in hidden], [17])
        self.assertEqual(active[0]["text"], "")
        self.assertIn("task_icons", active[0])
        self.assertIn("thumb_image_id", active[0])

    def test_matches_khID_alias(self):
        conn = _conn()
        _put(conn, 30, {"khID": "K9", "created": "2026-07-01T00:00:00",
                        "invoice": [{"sp": "A", "price": 80, "sl": 1}]})
        active, hidden = _load_customer_debt_orders(conn, "K9")
        self.assertEqual([o["thread_id"] for o in active], [30])
        self.assertEqual(hidden, [])


class BatchRemoval(unittest.TestCase):
    def test_find_and_remove_batch_across_orders(self):
        conn = _conn()
        # 3 đơn thuộc cùng 1 batch + 1 đơn có phiếu thu KHÁC (không đụng)
        _put(conn, 40, _order(payments=[{"amount": 100, "id": "a", "payment_batch_id": "B1"}]))
        _put(conn, 41, _order(payments=[{"amount": 200, "id": "b", "payment_batch_id": "B1"}]))
        _put(conn, 42, _order(payments=[
            {"amount": 50, "id": "c", "payment_batch_id": "B1"},
            {"amount": 5, "id": "d", "payment_batch_id": "OTHER"},
        ]))
        _put(conn, 43, _order(payments=[{"amount": 9, "id": "e"}]))   # không batch

        self.assertEqual(set(find_batch_thread_ids(conn, "B1")), {40, 41, 42})
        changed = remove_batch_payments(conn, "B1")
        self.assertEqual(set(changed), {40, 41, 42})

        # đơn 40/41 sạch payment; đơn 42 GIỮ phiếu OTHER; đơn 43 nguyên
        from order_store.serialization import get_order_by_thread_id
        self.assertEqual(get_order_by_thread_id(conn, 40)["payments"], [])
        self.assertEqual(get_order_by_thread_id(conn, 41)["payments"], [])
        kept = get_order_by_thread_id(conn, 42)["payments"]
        self.assertEqual([p["id"] for p in kept], ["d"])
        self.assertEqual([p["id"] for p in get_order_by_thread_id(conn, 43)["payments"]], ["e"])

        # batch đã hết → không còn đơn nào
        self.assertEqual(find_batch_thread_ids(conn, "B1"), [])


if __name__ == "__main__":
    unittest.main()
