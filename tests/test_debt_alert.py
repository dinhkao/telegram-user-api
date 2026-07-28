"""Tests cho cảnh báo CÔNG NỢ QUÁ HẠN (server_app/debt_alert.py).

Bọc luật thuần: mốc giao xong, đếm ngày theo giờ VN, gom theo khách (chỉ đơn đã
quá ngưỡng), loại đơn ẩn / bỏ theo dõi nợ / chưa giao. Không mạng, temp SQLite.
"""
from __future__ import annotations

import json
import sqlite3
import time
import unittest
from datetime import date, datetime, timedelta, timezone

from server_app.debt_alert import (
    SINCE, alert_line, compute_debt_alerts, created_date_vn, days_overdue, delivered_ts, money_vn,
)

_VN = timezone(timedelta(hours=7))

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

TODAY = date(2026, 7, 28)


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


def _cust(conn, key: str, name: str, kh_id="kv-1"):
    conn.execute("INSERT INTO customers (firebase_key, json, deleted_at) VALUES (?, ?, NULL)",
                 (key, json.dumps({"name": name, "kh_id": kh_id}, ensure_ascii=False)))


def _utc_iso(days_ago: int, hour_vn: int = 10) -> str:
    """Mốc giao hàng: `days_ago` ngày trước TODAY, giờ VN → chuỗi ISO UTC như app ghi."""
    vn = datetime(TODAY.year, TODAY.month, TODAY.day, hour_vn, tzinfo=_VN) - timedelta(days=days_ago)
    return vn.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _order(cust="K1", total=100, delivered_days_ago: int | None = 3, **extra):
    d = {
        "khach_hang_id": cust,
        "created": _utc_iso((delivered_days_ago or 0) + 1),
        "invoice": [{"sp": "A", "price": total, "sl": 1}],
    }
    if delivered_days_ago is not None:
        d["task_status"] = {"giao_hang": {"done": True, "skip": False, "at": _utc_iso(delivered_days_ago)}}
    d.update(extra)
    return d


class DeliveredAndDays(unittest.TestCase):
    def test_delivered_ts_reads_task_time(self):
        ts = delivered_ts(_order(delivered_days_ago=3))
        self.assertIsNotNone(ts)
        self.assertEqual(days_overdue(ts, TODAY), 3)

    def test_delivered_today_is_zero_days(self):
        self.assertEqual(days_overdue(delivered_ts(_order(delivered_days_ago=0)), TODAY), 0)

    def test_not_delivered_or_skipped_has_no_mark(self):
        self.assertIsNone(delivered_ts(_order(delivered_days_ago=None)))
        self.assertIsNone(delivered_ts({"task_status": {"giao_hang": {"done": False}}}))
        self.assertIsNone(delivered_ts({"task_status": {"giao_hang": {"done": True, "skip": True}}}))

    def test_legacy_order_falls_back_to_created(self):
        """Đơn cũ chỉ có cờ mirror `giao` → lấy ngày tạo làm mốc."""
        legacy = {"giao": True, "created": _utc_iso(5)}
        self.assertEqual(days_overdue(delivered_ts(legacy), TODAY), 5)

    def test_money_and_line_format(self):
        self.assertEqual(money_vn(4_200_000), "4.200.000đ")
        self.assertEqual(
            alert_line({"name": "Loan Phú", "days": 3, "order_count": 3, "total": 4_200_000}),
            "Loan Phú đang có công nợ đã 3 ngày chưa thanh toán từ 3 đơn hàng · 4.200.000đ")


class ComputeDebtAlerts(unittest.TestCase):
    def _fixture(self):
        conn = _conn()
        _cust(conn, "K1", "Loan Phú")
        _cust(conn, "K2", "Khách Hai")
        _cust(conn, "K3", "Khách Ba", kh_id=None)
        # K1: 3 đơn quá hạn (5, 3, 1 ngày) + 1 đơn giao hôm nay (chưa quá hạn)
        _put(conn, 10, _order(total=2_000_000, delivered_days_ago=5))
        _put(conn, 11, _order(total=1_200_000, delivered_days_ago=3))
        _put(conn, 12, _order(total=1_000_000, delivered_days_ago=1))
        _put(conn, 13, _order(total=900_000, delivered_days_ago=0))
        # Các đơn KHÔNG được tính
        _put(conn, 14, _order(total=500_000, delivered_days_ago=None))                 # chưa giao
        _put(conn, 15, _order(total=500_000, delivered_days_ago=4, bypass_debt=True))  # ẩn khỏi thu tiền
        _put(conn, 16, _order(total=500_000, delivered_days_ago=4, bo_theo_doi_no=1))  # bỏ theo dõi nợ
        _put(conn, 17, _order(total=500_000, delivered_days_ago=4,
                              payments=[{"amount": 500_000}]))                          # đã trả đủ
        _put(conn, 18, _order(total=500_000, delivered_days_ago=4), deleted=True)       # đã xoá
        # K2 nợ ít ngày hơn; K3 chưa liên kết KiotViet
        _put(conn, 20, _order(cust="K2", total=3_000_000, delivered_days_ago=2))
        _put(conn, 30, _order(cust="K3", total=700_000, delivered_days_ago=2))
        return conn

    def test_groups_by_customer_with_oldest_days(self):
        res = compute_debt_alerts(self._fixture(), 1, TODAY)
        self.assertEqual(res["count"], 3)
        first = res["alerts"][0]
        self.assertEqual(first["name"], "Loan Phú")
        self.assertEqual(first["days"], 5)                   # đơn quá hạn lâu nhất
        self.assertEqual(first["order_count"], 3)            # KHÔNG tính đơn giao hôm nay
        self.assertEqual(first["total"], 4_200_000)
        self.assertEqual(first["source_thread_id"], 10)      # đơn quá hạn cũ nhất
        self.assertFalse(first["blocked"])
        self.assertEqual(
            alert_line(first),
            "Loan Phú đang có công nợ đã 5 ngày chưa thanh toán từ 3 đơn hàng · 4.200.000đ")

    def test_sorted_by_days_then_money_and_flags_blocked(self):
        res = compute_debt_alerts(self._fixture(), 1, TODAY)
        self.assertEqual([a["name"] for a in res["alerts"]], ["Loan Phú", "Khách Hai", "Khách Ba"])
        self.assertTrue(res["alerts"][2]["blocked"])         # K3 chưa có kh_id KiotViet
        self.assertEqual(res["total"], 4_200_000 + 3_000_000 + 700_000)

    def test_threshold_filters_out_recent_debt(self):
        res = compute_debt_alerts(self._fixture(), 3, TODAY)
        self.assertEqual([a["name"] for a in res["alerts"]], ["Loan Phú"])
        self.assertEqual(res["alerts"][0]["order_count"], 2)   # chỉ đơn 5 ngày + 3 ngày
        self.assertEqual(res["alerts"][0]["total"], 3_200_000)
        self.assertEqual(res["min_days"], 3)

    def test_partial_payment_counts_remaining_only(self):
        conn = _conn()
        _cust(conn, "K9", "Khách Chín")
        _put(conn, 90, _order(cust="K9", total=1_000_000, delivered_days_ago=2,
                              payments=[{"amount": 400_000}]))
        res = compute_debt_alerts(conn, 1, TODAY)
        self.assertEqual(res["alerts"][0]["total"], 600_000)

    def test_orders_created_before_since_are_ignored(self):
        """Nợ cũ trước mốc (mặc định 01/07/2026) không nhắc — kể cả đã giao lâu."""
        conn = _conn()
        _cust(conn, "K1", "Loan Phú")
        old = _order(total=5_000_000, delivered_days_ago=40)
        old["created"] = "2026-06-20T03:00:00.000Z"          # trước mốc
        _put(conn, 10, old)
        _put(conn, 11, _order(total=800_000, delivered_days_ago=2))   # sau mốc
        res = compute_debt_alerts(conn, 1, TODAY)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["alerts"][0]["order_count"], 1)
        self.assertEqual(res["alerts"][0]["total"], 800_000)
        self.assertEqual(res["since"], SINCE.isoformat())

    def test_order_without_created_is_ignored(self):
        conn = _conn()
        _cust(conn, "K1", "Loan Phú")
        no_date = _order(total=900_000, delivered_days_ago=3)
        no_date.pop("created")
        _put(conn, 10, no_date)
        self.assertIsNone(created_date_vn(no_date))
        self.assertEqual(compute_debt_alerts(conn, 1, TODAY)["count"], 0)

    def test_custom_since_overrides_default(self):
        conn = _conn()
        _cust(conn, "K1", "Loan Phú")
        _put(conn, 10, _order(total=700_000, delivered_days_ago=3))   # tạo 4 ngày trước
        self.assertEqual(compute_debt_alerts(conn, 1, TODAY, date(2026, 7, 1))["count"], 1)
        self.assertEqual(compute_debt_alerts(conn, 1, TODAY, date(2026, 7, 27))["count"], 0)

    def test_no_alerts_when_nothing_overdue(self):
        conn = _conn()
        _cust(conn, "K1", "Loan Phú")
        _put(conn, 10, _order(total=100_000, delivered_days_ago=0))
        res = compute_debt_alerts(conn, 1, TODAY)
        self.assertEqual(res, {"alerts": [], "count": 0, "total": 0, "min_days": 1,
                               "since": SINCE.isoformat()})


class DailyPush(unittest.TestCase):
    """Bộ nhắc mỗi ngày: 1 thông báo/khách, quá trần thì gộp phần dư 1 dòng."""

    def _run(self, n_alerts: int):
        import server_app.notify as notify
        from server_app import debt_alert_daily as daily
        sent: list[tuple[str, str, dict]] = []
        original = notify.push_bg
        notify.push_bg = lambda title, body, data=None: sent.append((title, body, data or {}))
        try:
            alerts = [{"key": f"K{i}", "name": f"Khách {i}", "days": 3, "order_count": 2,
                       "total": 1_000_000, "source_thread_id": 100 + i} for i in range(n_alerts)]
            count = daily._push_alerts(alerts, sum(a["total"] for a in alerts))
        finally:
            notify.push_bg = original
        return sent, count

    def test_one_notification_per_customer(self):
        sent, count = self._run(3)
        self.assertEqual(count, 3)
        self.assertEqual(len(sent), 3)
        title, body, data = sent[0]
        self.assertEqual(title, "Công nợ quá hạn · Khách 0")
        self.assertEqual(body, "Khách 0 đang có công nợ đã 3 ngày chưa thanh toán từ 2 đơn hàng · 1.000.000đ")
        self.assertEqual(data["type"], "debt")           # NotifCenter mở trang thu tiền
        self.assertEqual(data["thread_id"], 100)         # đơn quá hạn cũ nhất của khách

    def test_over_cap_folds_the_rest_into_one(self):
        from server_app import debt_alert_daily as daily
        sent, count = self._run(daily.MAX_PUSH + 5)
        self.assertEqual(len(sent), daily.MAX_PUSH + 1)
        self.assertEqual(count, daily.MAX_PUSH + 1)
        self.assertIn("5 khách nợ quá hạn nữa", sent[-1][0])


if __name__ == "__main__":
    unittest.main()
