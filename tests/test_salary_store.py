"""Test lương THÁNG (salary_store): phụ cấp/thưởng upsert, ứng nhiều lần cộng dồn,
thực lãnh = lương + phụ cấp + thưởng − ứng. Thợ 'time' → lương SP = 0 (chờ chấm công).
"""
from __future__ import annotations

import os
import tempfile
import unittest

import salary_store
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class SalaryStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        salary_store.ensure_schema(self.conn)
        # 2 thợ, đặt loại 'time' để không phụ thuộc dữ liệu sản xuất
        self.a = add_worker(self.conn, "An")["id"]
        self.b = add_worker(self.conn, "Bình")["id"]
        update_worker(self.conn, self.a, wage_type="time")
        update_worker(self.conn, self.b, wage_type="time")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _row(self, data, wid):
        return next(r for r in data["workers"] if r["worker_id"] == wid)

    def test_month_range(self):
        self.assertEqual(salary_store.month_range("2026-02"), ("2026-02-01", "2026-02-28"))
        self.assertEqual(salary_store.month_range("2026-07"), ("2026-07-01", "2026-07-31"))

    def test_time_worker_luong_0_va_phu_cap_thuong(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=100_000, thuong=50_000)
        d = salary_store.compute_month_payroll(self.conn, "2026-07")
        r = self._row(d, self.a)
        self.assertEqual(r["wage_type"], "time")
        self.assertEqual(r["luong"], 0)              # thời gian → 0
        self.assertEqual(r["phu_cap"], 100_000)
        self.assertEqual(r["thuong"], 50_000)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 100k + 50k − 0

    def test_adjust_upsert_giu_field_khong_truyen(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=100_000)
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=20_000)  # không đụng phu_cap
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["phu_cap"], 100_000)
        self.assertEqual(r["thuong"], 20_000)

    def test_ung_nhieu_lan_cong_don_va_tru(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=200_000)
        salary_store.add_advance(self.conn, self.a, "2026-07", 30_000, adv_date="2026-07-05")
        salary_store.add_advance(self.conn, self.a, "2026-07", 20_000, adv_date="2026-07-10")
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["ung"], 50_000)
        self.assertEqual(r["adv_count"], 2)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 200k − 50k

    def test_xoa_ung_hoan_lai(self):
        adv = salary_store.add_advance(self.conn, self.b, "2026-07", 40_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 40_000)
        self.assertTrue(salary_store.delete_advance(self.conn, adv["id"]))
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 0)

    def test_advance_amount_phai_duong(self):
        with self.assertRaises(ValueError):
            salary_store.add_advance(self.conn, self.a, "2026-07", 0)

    def test_ung_tach_theo_thang(self):
        salary_store.add_advance(self.conn, self.a, "2026-07", 10_000)
        salary_store.add_advance(self.conn, self.a, "2026-08", 99_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)["ung"], 10_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["ung"], 99_000)


if __name__ == "__main__":
    unittest.main()
