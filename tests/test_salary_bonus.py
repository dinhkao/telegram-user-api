"""Test 2 khoản THƯỞNG bật/tắt theo tháng (salary_store/bonus.py + cờ trên salary_month).

- Chuyên cần: bật = đúng 200.000, không phụ thuộc ngày công.
- Vệ sinh: 12.000 × SỐ NGÀY CÔNG (đúng con số ở cột Công).
- 2 cờ này KHÔNG kế thừa sang tháng sau (khác mốc lương / trừ BHXH) — bật tháng nào
  chỉ ăn tháng đó, để khỏi âm thầm trả thừa ở tháng quên tắt.
"""
from __future__ import annotations

import os
import tempfile
import unittest

import attendance_store
import salary_store
from salary_store.bonus import THUONG_CHUYEN_CAN, THUONG_VE_SINH_MOI_NGAY, bonus_amounts
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class BonusPureTest(unittest.TestCase):
    """Luật thuần — không đụng DB."""

    def test_tat_het_thi_khong_co_gi(self):
        self.assertEqual(bonus_amounts(26, chuyen_can=False, ve_sinh=False), (0.0, 0.0))

    def test_chuyen_can_co_dinh_khong_theo_cong(self):
        for cong in (0, 1, 26, 31):
            cc, _ = bonus_amounts(cong, chuyen_can=True, ve_sinh=False)
            self.assertEqual(cc, THUONG_CHUYEN_CAN)

    def test_ve_sinh_nhan_theo_ngay_cong(self):
        _, vs = bonus_amounts(24, chuyen_can=False, ve_sinh=True)
        self.assertEqual(vs, 24 * THUONG_VE_SINH_MOI_NGAY)

    def test_ve_sinh_cong_le_van_tinh(self):
        _, vs = bonus_amounts(25.5, chuyen_can=False, ve_sinh=True)
        self.assertEqual(vs, 25.5 * THUONG_VE_SINH_MOI_NGAY)

    def test_khong_cham_cong_thi_ve_sinh_bang_0(self):
        _, vs = bonus_amounts(0, chuyen_can=False, ve_sinh=True)
        self.assertEqual(vs, 0.0)
        _, vs_am = bonus_amounts(-3, chuyen_can=False, ve_sinh=True)   # dữ liệu hỏng
        self.assertEqual(vs_am, 0.0)


class BonusMonthTest(unittest.TestCase):
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

    def _cham_cong(self, ngay: list[str], code: str = "77"):
        """Mỗi ngày đủ 2 ca = 1 công (không tăng ca)."""
        attendance_store.map_employee_code(self.conn, code, self.a)
        for day in ngay:
            for t in ("07:00", "11:00", "13:00", "17:00"):
                attendance_store.add_manual(self.conn, code, day, t)

    def test_mac_dinh_tat(self):
        r = self._row("2026-08")
        self.assertFalse(r["cc_on"])
        self.assertFalse(r["vs_on"])
        self.assertEqual(r["thuong_cc"], 0)
        self.assertEqual(r["thuong_vs"], 0)

    def test_bat_chuyen_can_cong_vao_thuc_lanh(self):
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=True)
        r = self._row("2026-08")
        self.assertTrue(r["cc_on"])
        self.assertEqual(r["thuong_cc"], THUONG_CHUYEN_CAN)
        self.assertEqual(r["thuc_lanh"], r["luong"] + THUONG_CHUYEN_CAN)

    def test_ve_sinh_theo_dung_so_cong_hien_o_cot_cong(self):
        self._cham_cong(["2026-08-03", "2026-08-04", "2026-08-05"])
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_vs=True)
        r = self._row("2026-08")
        self.assertEqual(r["cong"], 3)
        self.assertEqual(r["thuong_vs"], 3 * THUONG_VE_SINH_MOI_NGAY)

    def test_hai_thuong_cong_don_va_vao_tong_cot(self):
        self._cham_cong(["2026-08-03", "2026-08-04"])
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=True, thuong_vs=True)
        d = salary_store.compute_month_payroll(self.conn, "2026-08")
        r = next(x for x in d["workers"] if x["worker_id"] == self.a)
        self.assertEqual(r["thuong_cc"], THUONG_CHUYEN_CAN)
        self.assertEqual(r["thuong_vs"], 2 * THUONG_VE_SINH_MOI_NGAY)
        self.assertEqual(r["thuc_lanh"], r["luong"] + r["thuong_cc"] + r["thuong_vs"])
        self.assertEqual(d["totals"]["thuong_cc"], THUONG_CHUYEN_CAN)
        self.assertEqual(d["totals"]["thuong_vs"], 2 * THUONG_VE_SINH_MOI_NGAY)
        self.assertEqual(d["totals"]["thuc_lanh"], sum(x["thuc_lanh"] for x in d["workers"]))

    def test_khong_ke_thua_sang_thang_sau(self):
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=True, thuong_vs=True)
        self.assertTrue(self._row("2026-08")["cc_on"])
        r9 = self._row("2026-09")            # THÁNG SAU phải sạch
        self.assertFalse(r9["cc_on"])
        self.assertFalse(r9["vs_on"])
        self.assertEqual(r9["thuong_cc"], 0)

    def test_tat_lai_thi_het_thuong(self):
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=True)
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=False)
        r = self._row("2026-08")
        self.assertFalse(r["cc_on"])
        self.assertEqual(r["thuong_cc"], 0)

    def test_bat_thuong_khong_de_len_o_khac_cua_thang(self):
        salary_store.set_month_adjust(self.conn, "2026-08", self.a,
                                      thuong=150_000, note="ghi chú", weekly=True)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 7_000_000)
        salary_store.set_month_bhxh(self.conn, "2026-08", self.a, 500_000)
        salary_store.set_month_adjust(self.conn, "2026-08", self.a, thuong_cc=True)
        r = self._row("2026-08")
        self.assertEqual(r["thuong"], 150_000)
        self.assertEqual(r["note"], "ghi chú")
        self.assertTrue(r["weekly"])
        self.assertEqual(r["monthly_salary"], 7_000_000)
        self.assertEqual(r["bhxh"], 500_000)
        self.assertTrue(r["cc_on"])


if __name__ == "__main__":
    unittest.main()
