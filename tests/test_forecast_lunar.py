"""Âm lịch (forecast_store.lunar): mốc Tết/Trung thu đã kiểm, tháng nhuận 2025, can chi,
find_solar cùng ngày âm năm ngoái, sự kiện kế tiếp."""
from __future__ import annotations

import datetime as dt
import unittest

from forecast_store.lunar import (can_chi, find_solar, lunar_label, next_lunar_event,
                                  solar2lunar)


class LunarTest(unittest.TestCase):
    def test_moc_da_biet(self):
        self.assertEqual(solar2lunar(17, 2, 2026), (1, 1, 2026, 0))    # Tết Bính Ngọ
        self.assertEqual(solar2lunar(29, 1, 2025), (1, 1, 2025, 0))    # Tết Ất Tỵ
        self.assertEqual(solar2lunar(6, 10, 2025), (15, 8, 2025, 0))   # Trung thu 2025
        self.assertEqual(solar2lunar(25, 9, 2026), (15, 8, 2026, 0))   # Trung thu 2026
        self.assertEqual(solar2lunar(6, 2, 2027), (1, 1, 2027, 0))     # Tết Đinh Mùi

    def test_thang_nhuan_2025(self):
        # 2025 nhuận tháng 6: 25/7/2025 là 1/6 nhuận
        self.assertEqual(solar2lunar(25, 7, 2025)[1:], (6, 2025, 1))
        self.assertEqual(solar2lunar(25, 6, 2025)[1:], (6, 2025, 0))

    def test_can_chi_label(self):
        self.assertEqual(can_chi(2026), "Bính Ngọ")
        self.assertEqual(can_chi(2025), "Ất Tỵ")
        self.assertEqual(lunar_label(dt.date(2026, 9, 8)), "28/7 ÂL Bính Ngọ")
        self.assertTrue(lunar_label(dt.date(2025, 7, 25)).startswith("1/6N"))

    def test_find_solar_cung_ngay_am_nam_ngoai(self):
        self.assertEqual(find_solar(28, 7, dt.date(2025, 9, 8)), dt.date(2025, 9, 19))
        self.assertEqual(find_solar(15, 8, dt.date(2025, 10, 1)), dt.date(2025, 10, 6))
        # ngày 15/6 quanh mùa nhuận 2025: ưu tiên tháng KHÔNG nhuận (9/7), không phải 8/8
        self.assertEqual(find_solar(15, 6, dt.date(2025, 7, 20)), dt.date(2025, 7, 9))

    def test_next_event(self):
        e = next_lunar_event(15, 8, dt.date(2026, 9, 8), "Trung thu")
        self.assertEqual((e["ymd"], e["days"]), ("2026-09-25", 17))
        t = next_lunar_event(1, 1, dt.date(2026, 9, 8), "Tết")
        self.assertEqual(t["ymd"], "2027-02-06")


if __name__ == "__main__":
    unittest.main()
