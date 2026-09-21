"""Business-rule regression tests for product_store.profit.calculate_order_profit.

Money math: revenue/cost/profit per item + VAT/PVC/discount fees. Pure when all
items carry a frozen cost_price (then get_product is never called, so conn=None).
Quy ước giá vốn đã gồm khoản VAT bán ra phải chịu; lãi dùng tổng thu gồm VAT.
"""
from __future__ import annotations

import unittest

from product_store.profit import calculate_order_profit


class OrderProfit(unittest.TestCase):
    def test_single_frozen_item(self):
        order = {"invoice": [{"sp": "sp1", "sl": 10, "price": 5000, "cost_price": 3000}],
                 "vat": 0, "pvc": 0, "discount": 0}
        r = calculate_order_profit(None, order)
        self.assertEqual(r["total_revenue"], 50000)
        self.assertEqual(r["total_cost"], 30000)
        self.assertEqual(r["total_profit"], 20000)
        item = r["items"][0]
        self.assertEqual(item["code"], "SP1")              # uppercased
        self.assertTrue(item["is_frozen"])
        self.assertTrue(item["has_cost"])

    def test_vat_offsets_output_tax_provision_already_in_cost(self):
        order = {"invoice": [{"sp": "sp1", "sl": 1, "price": 10000, "cost_price": 6000}],
                 "vat": 800, "pvc": 200, "discount": 300}   # customer pays 10700; net revenue 9900
        r = calculate_order_profit(None, order)
        self.assertEqual(r["fees"]["fee_total"], 700)
        self.assertEqual(r["total_revenue"], 9900)
        self.assertEqual(r["total_profit"], 4700)
        self.assertEqual(r["customer_total"], 10700)

    def test_unknown_cost_has_no_complete_profit(self):
        # cost_price frozen at 0 -> has_cost False, profit 0, total_profit 0
        order = {"invoice": [{"sp": "x", "sl": 5, "price": 1000, "cost_price": 0}]}
        r = calculate_order_profit(None, order)
        self.assertEqual(r["total_profit"], 0)
        self.assertFalse(r["items"][0]["has_cost"])
        self.assertIsNone(r["complete_profit"])
        self.assertIsNone(r["items"][0]["profit"])

    def test_empty_invoice(self):
        r = calculate_order_profit(None, {"invoice": []})
        self.assertEqual((r["item_count"], r["total_profit"], r["total_revenue"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
