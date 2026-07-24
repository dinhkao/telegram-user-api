"""utils/qty.py — parse/format SL hoá đơn (số lẻ, chuỗi VN, NaN guard)."""
import unittest

from utils.qty import parse_qty, qty_for_api, fmt_qty, line_total


class ParseQty(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_qty(3), 3.0)
        self.assertEqual(parse_qty(3.5), 3.5)
        self.assertEqual(parse_qty(0), 0.0)

    def test_strings(self):
        self.assertEqual(parse_qty("3"), 3.0)
        self.assertEqual(parse_qty("3.5"), 3.5)
        self.assertEqual(parse_qty("3,5"), 3.5)
        self.assertEqual(parse_qty("1.234.567"), 1234567.0)   # phân cách nghìn

    def test_garbage(self):
        self.assertEqual(parse_qty(None), 0.0)
        self.assertEqual(parse_qty(""), 0.0)
        self.assertEqual(parse_qty("abc"), 0.0)
        self.assertEqual(parse_qty(float("nan")), 0.0)
        self.assertEqual(parse_qty(float("inf")), 0.0)
        self.assertEqual(parse_qty("NaN"), 0.0)
        self.assertEqual(parse_qty("Infinity"), 0.0)


class QtyForApi(unittest.TestCase):
    def test_integral_stays_int(self):
        self.assertEqual(qty_for_api(3), 3)
        self.assertIsInstance(qty_for_api(3), int)

    def test_fractional_rounded_3(self):
        self.assertEqual(qty_for_api(3.5), 3.5)
        self.assertEqual(qty_for_api(1 / 3), 0.333)

    def test_default(self):
        self.assertEqual(qty_for_api(None, default=1), 1)


class FmtQty(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt_qty(3), "3")
        self.assertEqual(fmt_qty(3.5), "3,5")


class LineTotal(unittest.TestCase):
    def test_fractional_line(self):
        # 3,5 × 135.000 = 472.500 — bug cũ int(sl) tính 405.000
        self.assertEqual(line_total(135000, 3.5), 472500)

    def test_rounding_to_dong(self):
        self.assertEqual(line_total(1000, 0.333), 333)

    def test_garbage(self):
        self.assertEqual(line_total(float("nan"), 5), 0)
        self.assertEqual(line_total(1000, "NaN"), 0)


if __name__ == "__main__":
    unittest.main()
