"""Pure unit tests for payment_store.domain — no KiotViet, no DB.

The payment decision logic extracted from _process_payment_core, now testable in
isolation. Each resolve_payment_target branch mirrors the original inline checks.
"""
from __future__ import annotations

import unittest

from payment_store.domain import method_params, resolve_payment_target, build_payment_record


class MethodParams(unittest.TestCase):
    def test_transfer(self):
        self.assertEqual(method_params("Transfer"), (1, "CK"))

    def test_cash(self):
        self.assertEqual(method_params("Cash"), (None, "TM"))


class ResolvePaymentTarget(unittest.TestCase):
    def test_no_order(self):
        kh, kv, name, err = resolve_payment_target(None, None)
        self.assertEqual((kh, kv, name), (None, None, None))
        self.assertEqual(err, "Không tìm thấy đơn hàng")

    def test_order_without_customer_ref(self):
        kh, kv, name, err = resolve_payment_target({"khach_hang": "Tú"}, None)
        self.assertIsNone(kh)          # no kh_id_fb -> stays None (result field not set)
        self.assertEqual(err, "Đơn hàng này chưa được gán khách hàng.")

    def test_customer_ref_but_no_kiotviet_id(self):
        # kh_id_fb known (result gets it) but the customer row is missing / has no kv id
        kh, kv, name, err = resolve_payment_target({"khach_hang_id": "FB1"}, None)
        self.assertEqual(kh, "FB1")
        self.assertIsNone(kv)
        self.assertEqual(err, "Không tìm thấy thông tin khách hàng hoặc ID KiotViet.")

        kh, kv, name, err = resolve_payment_target({"khach_hang_id": "FB1"}, {"kh_id": None})
        self.assertEqual((kh, kv, err[:20]), ("FB1", None, "Không tìm thấy thông"))

    def test_success_prefers_customer_name(self):
        kh, kv, name, err = resolve_payment_target(
            {"khach_hang_id": "FB1", "khach_hang": "OrderName"},
            {"kh_id": 999, "name": "CustName"},
        )
        self.assertEqual((kh, kv, name, err), ("FB1", 999, "CustName", None))

    def test_success_falls_back_to_order_name_then_id(self):
        kh, kv, name, err = resolve_payment_target(
            {"khach_hang_id": "FB1", "khach_hang": "OrderName"}, {"kh_id": 999})
        self.assertEqual(name, "OrderName")     # no customer name -> order name
        kh, kv, name, err = resolve_payment_target({"khID": "FB2"}, {"kh_id": 7})
        self.assertEqual((kh, name), ("FB2", "FB2"))   # falls back to str(kh_id_fb); khID alias works


class BuildPaymentRecord(unittest.TestCase):
    def test_shape(self):
        rec = build_payment_record(50000, "Cash", {"code": "PT01"}, "actor")
        self.assertEqual(rec, {"amount": 50000, "method": "Cash",
                               "kiotvietData": {"code": "PT01"}, "createdBy": "actor"})


if __name__ == "__main__":
    unittest.main()
