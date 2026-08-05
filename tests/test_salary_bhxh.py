"""Test TRỪ BHXH theo TỪNG THÁNG (salary_store/bhxh.py).

Luật kế thừa giống mốc lương: đặt ở tháng nào áp từ tháng đó TRỞ ĐI, tháng TRƯỚC
không đổi; chưa đặt bao giờ → 0 (không trừ). Chỗ KHÁC mốc và là lý do có file test
riêng: số 0 ở đây CÓ NGHĨA ("từ tháng này thôi đóng BHXH") nên phải phân biệt được
với "bỏ đặt riêng tháng này" (= None).
"""
from __future__ import annotations

import os
import tempfile
import unittest

import attendance_store
import salary_store
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class SalaryBhxhTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        salary_store.ensure_schema(self.conn)
        attendance_store.ensure_schema(self.conn)
        self.a = add_worker(self.conn, "An")["id"]
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=6_500_000)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _row(self, ym):
        d = salary_store.compute_month_payroll(self.conn, ym)
        return next(r for r in d["workers"] if r["worker_id"] == self.a)

    # ── luật kế thừa / không đụng quá khứ ────────────────────────────────────────

    def test_chua_dat_thi_khong_tru(self):
        r = self._row("2026-07")
        self.assertEqual(r["bhxh"], 0)
        self.assertEqual(r["bhxh_ym"], "")
        self.assertFalse(r["bhxh_own"])

    def test_dat_thang_nao_ap_tu_thang_do_tro_di(self):
        salary_store.set_month_bhxh(self.conn, "2026-07", self.a, 682_500, by="duy")
        self.assertEqual(self._row("2026-06")["bhxh"], 0)          # QUÁ KHỨ không đổi
        r7 = self._row("2026-07")
        self.assertEqual(r7["bhxh"], 682_500)
        self.assertEqual(r7["bhxh_ym"], "2026-07")
        self.assertTrue(r7["bhxh_own"])                            # đặt riêng tháng này
        r8 = self._row("2026-08")
        self.assertEqual(r8["bhxh"], 682_500)                      # tháng sau KẾ THỪA
        self.assertEqual(r8["bhxh_ym"], "2026-07")
        self.assertFalse(r8["bhxh_own"])                           # nhưng KHÔNG đặt riêng

    def test_sua_thang_sau_khong_lam_doi_thang_truoc(self):
        salary_store.set_month_bhxh(self.conn, "2026-06", self.a, 600_000)
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, 750_000)
        self.assertEqual(self._row("2026-06")["bhxh"], 600_000)
        self.assertEqual(self._row("2026-07")["bhxh"], 600_000)    # kế thừa tháng 6
        self.assertEqual(self._row("2026-08")["bhxh"], 750_000)

    # ── 0 KHÁC "bỏ đặt riêng" (điểm khác mốc lương) ──────────────────────────────

    def test_dat_bang_0_la_dung_tru_tu_thang_nay(self):
        salary_store.set_month_bhxh(self.conn, "2026-06", self.a, 600_000)
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, 0)
        self.assertEqual(self._row("2026-07")["bhxh"], 600_000)
        r8 = self._row("2026-08")
        self.assertEqual(r8["bhxh"], 0)
        self.assertTrue(r8["bhxh_own"])                            # 0 vẫn là bản ĐẶT RIÊNG
        self.assertEqual(self._row("2026-09")["bhxh"], 0)          # tháng sau kế thừa số 0

    def test_bo_dat_rieng_thi_ke_thua_lai(self):
        salary_store.set_month_bhxh(self.conn, "2026-06", self.a, 600_000)
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, 750_000)
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, None)   # bỏ đặt riêng
        r8 = self._row("2026-08")
        self.assertEqual(r8["bhxh"], 600_000)                      # về kế thừa tháng 6
        self.assertEqual(r8["bhxh_ym"], "2026-06")
        self.assertFalse(r8["bhxh_own"])

    def test_so_am_ep_ve_0(self):
        salary_store.set_month_bhxh(self.conn, "2026-07", self.a, -50_000)
        self.assertEqual(self._row("2026-07")["bhxh"], 0)

    # ── không đụng ô khác của tháng + vào đúng thực lãnh ─────────────────────────

    def test_bhxh_khong_de_len_thuong_ghi_chu_luong_tuan_moc(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a,
                                      thuong=200_000, note="ghi chú", weekly=True)
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 7_000_000)
        salary_store.set_month_bhxh(self.conn, "2026-07", self.a, 500_000)
        r = self._row("2026-07")
        self.assertEqual(r["thuong"], 200_000)
        self.assertEqual(r["note"], "ghi chú")
        self.assertTrue(r["weekly"])
        self.assertEqual(r["monthly_salary"], 7_000_000)
        self.assertEqual(r["bhxh"], 500_000)

    def test_thuc_lanh_tru_bhxh_va_tong_cot(self):
        salary_store.add_allowance(self.conn, self.a, "2026-07", 300_000, note="ăn trưa")
        salary_store.add_advance(self.conn, self.a, "2026-07", 1_000_000)
        salary_store.set_month_bhxh(self.conn, "2026-07", self.a, 500_000)
        d = salary_store.compute_month_payroll(self.conn, "2026-07")
        r = next(x for x in d["workers"] if x["worker_id"] == self.a)
        # lương = 0 (chưa chấm công) → 0 + 300k − 1tr − 500k
        self.assertEqual(r["thuc_lanh"], r["luong"] + 300_000 - 1_000_000 - 500_000)
        self.assertEqual(d["totals"]["bhxh"], 500_000)
        # TỔNG cột Lãnh chỉ cộng thợ DƯƠNG (2026-08-05): thợ này đang âm nên vào
        # thuc_lanh_am, không kéo tổng xuống — xem compute_month_payroll.
        self.assertEqual(d["totals"]["thuc_lanh"],
                         sum(max(0, x["thuc_lanh"]) for x in d["workers"]))
        self.assertEqual(d["totals"]["thuc_lanh_am"],
                         sum(-x["thuc_lanh"] for x in d["workers"] if x["thuc_lanh"] < 0))

    def test_lich_su_bhxh_cua_tho(self):
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, 750_000, by="duy")
        salary_store.set_month_bhxh(self.conn, "2026-06", self.a, 600_000, by="duy")
        h = salary_store.list_worker_bhxh(self.conn, self.a)
        self.assertEqual([(x["ym"], x["value"]) for x in h],
                         [("2026-06", 600_000.0), ("2026-08", 750_000.0)])


if __name__ == "__main__":
    unittest.main()
