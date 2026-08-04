"""Test PIVOT lương SP (production_store/wage_pivot.py) — phần logic thuần.

Trọng tâm: SẮP XẾP PHIẾU THEO GIỜ phải quy về PHÚT. So chuỗi thì "7:00" đứng sau
"13:00" (lỗi thật đã gặp ở view chi tiết), và phiếu không ghi giờ phải xếp CUỐI.
"""
from __future__ import annotations

import unittest

from production_store.wage_pivot import _all_days, _time_key


class TimeKeyTest(unittest.TestCase):
    def test_gio_mot_chu_so_van_dung_thu_tu(self):
        self.assertLess(_time_key("7:00"), _time_key("10:30"))
        self.assertLess(_time_key("9:15"), _time_key("13:00"))

    def test_hai_cach_viet_gio_bang_nhau(self):
        self.assertEqual(_time_key("07:00"), _time_key("7:00"))

    def test_khong_co_gio_thi_xep_cuoi(self):
        self.assertGreater(_time_key(""), _time_key("23:59"))
        self.assertGreater(_time_key(None), _time_key("23:59"))
        self.assertGreater(_time_key("linh tinh"), _time_key("23:59"))

    def test_sap_xep_ca_danh_sach(self):
        raw = ["13:00", "7:00", "", "10:30", "9:00"]
        self.assertEqual(sorted(raw, key=_time_key), ["7:00", "9:00", "10:30", "13:00", ""])


class AllDaysTest(unittest.TestCase):
    def test_du_moi_ngay_trong_thang(self):
        self.assertEqual(len(_all_days("2026-07-01", "2026-07-31")), 31)
        self.assertEqual(_all_days("2026-07-01", "2026-07-03"),
                         ["2026-07-01", "2026-07-02", "2026-07-03"])

    def test_moc_hong_hoac_qua_dai_thi_rong(self):
        self.assertEqual(_all_days("hỏng", "2026-07-31"), [])
        self.assertEqual(_all_days("2026-07-31", "2026-07-01"), [])   # ngược
        self.assertEqual(_all_days("2020-01-01", "2026-07-31"), [])   # > 400 ngày


if __name__ == "__main__":
    unittest.main()
