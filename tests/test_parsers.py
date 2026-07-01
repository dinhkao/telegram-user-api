"""Characterization tests for the order-text parsers (pure business logic).

These lock the current behavior of the Vietnamese order parsing — the core, and
previously untested, domain rules. Both parsers are pure here: parse_comma_text
skips the DB when kh_id is None; parse_invoice_free_text takes an injected
_all_products list. Values were captured from the running code, so these tests
document reality (change them only with intent).
"""
from __future__ import annotations

import unittest

from order_store.comma_parser import _parse_no_qc, _parse_qc, parse_comma_text
from order_store.free_text import parse_invoice_free_text

PRODUCTS = [{"code": "SP1"}, {"code": "KDXDB"}, {"code": "DM180"}]


class ParseQc(unittest.TestCase):
    def test_quy_cach_tokens(self):
        self.assertEqual(_parse_qc(""), (None, [1]))
        self.assertEqual(_parse_qc("5t"), ("t", [5]))        # 5 thùng
        self.assertEqual(_parse_qc("3b"), ("b", [3]))        # 3 bao
        self.assertEqual(_parse_qc("2t3b"), ("tb", [2, 3]))  # combo
        self.assertEqual(_parse_qc("t5"), ("t5", [1]))       # tx form kept as-is
        self.assertEqual(_parse_qc("xyz"), (None, [1]))


class ParseNoQc(unittest.TestCase):
    def test_requires_double_space(self):
        self.assertEqual(_parse_no_qc("SP1  10"), {"sp": "SP1", "sl1qc": "10", "price": None, "note": None})
        self.assertEqual(_parse_no_qc("SP1  10 5000 ghi chu"),
                         {"sp": "SP1", "sl1qc": "10", "price": "5000", "note": "ghi chu"})
        self.assertIsNone(_parse_no_qc("SP1 10"))            # single space -> no match
        self.assertIsNone(_parse_no_qc("nope"))


class ParseCommaText(unittest.TestCase):
    def _one(self, text):
        out = parse_comma_text(text, None, None)   # conn unused when kh_id is None
        return out

    def test_carton_multiplies_quantity(self):
        self.assertEqual(self._one("SP1 5t 10"),
                         [{"sp": "SP1", "so_qc": [5], "qc_type": "t", "sl1pc": 10.0, "sl": 50, "price": 0, "note": None}])

    def test_plain_code_qty(self):
        self.assertEqual(self._one("ABC 3"),
                         [{"sp": "ABC", "so_qc": [1], "qc_type": None, "sl1pc": 3.0, "sl": 3, "price": 0, "note": None}])

    def test_double_space_form_with_price_and_note(self):
        self.assertEqual(self._one("SP1  10  5000  note"),
                         [{"sp": "SP1", "so_qc": [1], "qc_type": None, "sl1pc": 10.0, "sl": 10, "price": 5000, "note": "note"}])

    def test_multiline_and_uppercasing(self):
        self.assertEqual(self._one("x1 2b 3\nY2 4"), [
            {"sp": "X1", "so_qc": [2], "qc_type": "b", "sl1pc": 3.0, "sl": 6, "price": 0, "note": None},
            {"sp": "Y2", "so_qc": [1], "qc_type": None, "sl1pc": 4.0, "sl": 4, "price": 0, "note": None},
        ])

    def test_trailing_tao_hd_is_stripped(self):
        self.assertEqual(self._one("SP1 5t 10\ntao hd"),
                         [{"sp": "SP1", "so_qc": [5], "qc_type": "t", "sl1pc": 10.0, "sl": 50, "price": 0, "note": None}])


class ParseInvoiceFreeText(unittest.TestCase):
    def _one(self, text):
        return parse_invoice_free_text(None, text, None, _all_products=PRODUCTS)

    def test_plain_qty(self):
        self.assertEqual(self._one("SP1 10"),
                         [{"sp": "SP1", "so_qc": [1], "qc_type": None, "sl1pc": 10, "sl": 10, "price": 0, "note": None}])

    def test_carton_defaults_to_50_per_unit(self):
        self.assertEqual(self._one("SP1 2t"),
                         [{"sp": "SP1", "so_qc": [2], "qc_type": "t", "sl1pc": 50, "sl": 100, "price": 0, "note": None}])

    def test_carton_explicit_count(self):
        self.assertEqual(self._one("SP1 2t 30"),
                         [{"sp": "SP1", "so_qc": [2], "qc_type": "t", "sl1pc": 30, "sl": 60, "price": 0, "note": None}])

    def test_kdxdb_special_default_is_5(self):
        self.assertEqual(self._one("KDXDB 1t"),
                         [{"sp": "KDXDB", "so_qc": [1], "qc_type": "t", "sl1pc": 5, "sl": 5, "price": 0, "note": None}])

    def test_dm180_loc_rewrite(self):
        # "DM180 2 lốc" is rewritten to "DM180 2b 12" -> 2 bao * 12
        self.assertEqual(self._one("DM180 2 loc"),
                         [{"sp": "DM180", "so_qc": [2], "qc_type": "b", "sl1pc": 12, "sl": 24, "price": 0, "note": None}])

    def test_unknown_code_dropped(self):
        self.assertEqual(self._one("unknown 5"), [])


if __name__ == "__main__":
    unittest.main()
