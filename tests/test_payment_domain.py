"""Pure unit tests for payment_store.domain — no KiotViet, no DB.

The payment decision logic extracted from _process_payment_core, now testable in
isolation. Each resolve_payment_target branch mirrors the original inline checks.
"""
from __future__ import annotations

import unittest

from payment_store.domain import (
    method_params, resolve_payment_target, build_payment_record, compute_debt, allocate_payment,
)


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


class ComputeDebt(unittest.TestCase):
    def test_empty_order(self):
        self.assertEqual(compute_debt({}), {"total": 0, "paid": 0, "remaining": 0})

    def test_total_minus_payments(self):
        d = compute_debt({"tong_cong": 100000, "payments": [{"amount": 30000}, {"amount": 20000}]})
        self.assertEqual(d, {"total": 100000, "paid": 50000, "remaining": 50000})

    def test_total_field_fallback(self):
        self.assertEqual(compute_debt({"total": 500}), {"total": 500, "paid": 0, "remaining": 500})

    def test_tong_cong_takes_precedence_over_total(self):
        self.assertEqual(compute_debt({"tong_cong": 100, "total": 999})["total"], 100)


class BuildPaymentRecord(unittest.TestCase):
    def test_shape(self):
        rec = build_payment_record(50000, "Cash", {"code": "PT01"}, "actor")
        self.assertEqual(rec, {"amount": 50000, "method": "Cash",
                               "kiotvietData": {"code": "PT01"}, "createdBy": "actor"})


class AllocatePayment(unittest.TestCase):
    def _orders(self):
        # đã sắp cũ→mới
        return [{"thread_id": 1, "debt": 100}, {"thread_id": 2, "debt": 200}, {"thread_id": 3, "debt": 50}]

    def test_fills_one_order_fully(self):
        self.assertEqual(allocate_payment(self._orders(), 100), [{"thread_id": 1, "amount": 100}])

    def test_fills_multiple_orders_oldest_first(self):
        # 250 = trả đủ đơn 1 (100) + đủ đơn 2 (150 còn thiếu? không — đơn 2 cần 200) →
        # 250 = 100 (đơn 1) + 150 (đơn 2 một phần)
        self.assertEqual(
            allocate_payment(self._orders(), 250),
            [{"thread_id": 1, "amount": 100}, {"thread_id": 2, "amount": 150}],
        )

    def test_last_order_partial(self):
        # 310 = 100 + 200 + 10 (đơn cuối một phần)
        self.assertEqual(
            allocate_payment(self._orders(), 310),
            [{"thread_id": 1, "amount": 100}, {"thread_id": 2, "amount": 200}, {"thread_id": 3, "amount": 10}],
        )

    def test_amount_equals_total_debt(self):
        self.assertEqual(
            allocate_payment(self._orders(), 350),
            [{"thread_id": 1, "amount": 100}, {"thread_id": 2, "amount": 200}, {"thread_id": 3, "amount": 50}],
        )

    def test_zero_amount_rejected(self):
        with self.assertRaises(ValueError):
            allocate_payment(self._orders(), 0)

    def test_negative_amount_rejected(self):
        with self.assertRaises(ValueError):
            allocate_payment(self._orders(), -5)

    def test_amount_over_total_debt_rejected(self):
        with self.assertRaises(ValueError):
            allocate_payment(self._orders(), 351)

    def test_empty_orders_always_rejects(self):
        with self.assertRaises(ValueError):
            allocate_payment([], 100)

    def test_skips_zero_debt_orders(self):
        orders = [{"thread_id": 1, "debt": 0}, {"thread_id": 2, "debt": 100}]
        self.assertEqual(allocate_payment(orders, 60), [{"thread_id": 2, "amount": 60}])


if __name__ == "__main__":
    unittest.main()
