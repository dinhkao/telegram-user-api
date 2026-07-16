"""Unit tests purchase_store + supplier_store — SQLite tạm (không đụng app.db)."""
from __future__ import annotations

import os
import tempfile
import unittest

from purchase_store import (add_purchase, add_purchase_payment, count_all_purchases,
                            delete_purchase_payment, get_purchase, get_purchase_full,
                            list_all_purchases, list_purchases_for_supplier,
                            payments_for_cashbox, soft_delete_purchase,
                            update_purchase_items)
from supplier_store import (add_supplier, get_supplier, list_suppliers,
                            soft_delete_supplier, update_supplier)
from utils.db import get_connection


class PurchaseSupplierStore(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "test.db")
        self.conn = get_connection(self.db)

    def tearDown(self):
        self.conn.close()

    def test_supplier_crud(self):
        s = add_supplier(self.conn, "Cty Bao Bì A", phone="0901", address="Q5", by="duy")
        self.assertEqual(s["name"], "Cty Bao Bì A")
        update_supplier(self.conn, s["id"], phone="0999", note="giao thứ 2")
        s2 = get_supplier(self.conn, s["id"])
        self.assertEqual(s2["phone"], "0999")
        self.assertEqual(s2["name"], "Cty Bao Bì A")  # ô không gửi giữ nguyên
        soft_delete_supplier(self.conn, s["id"], by="duy")
        self.assertIsNotNone(get_supplier(self.conn, s["id"])["deleted_at"])
        self.assertEqual(list_suppliers(self.conn), [])  # xoá mềm → khỏi list

    def test_purchase_flow(self):
        s = add_supplier(self.conn, "NCC B")
        items = [{"sp": "KDX", "sl": 10, "price": 5000}, {"sp": "KGL", "sl": 2, "price": 0}]
        p = add_purchase(self.conn, s["id"], items, 50000, note="đợt 1", by="trang")
        self.assertEqual(p["total"], 50000)
        self.assertEqual(len(p["items"]), 2)
        full = get_purchase_full(self.conn, p["id"])
        self.assertEqual(full["supplier_name"], "NCC B")
        # sửa items + đổi tổng
        update_purchase_items(self.conn, p["id"], [{"sp": "KDX", "sl": 5, "price": 4000}], 20000, "sửa")
        p2 = get_purchase(self.conn, p["id"])
        self.assertEqual(p2["total"], 20000)
        self.assertEqual(p2["note"], "sửa")

    def test_dashboard_and_stats(self):
        a = add_supplier(self.conn, "A")
        b = add_supplier(self.conn, "B")
        add_purchase(self.conn, a["id"], [{"sp": "X", "sl": 1, "price": 100}], 100)
        add_purchase(self.conn, a["id"], [{"sp": "Y", "sl": 2, "price": 50}], 100)
        add_purchase(self.conn, b["id"], [{"sp": "Z", "sl": 1, "price": 999}], 999)
        self.assertEqual(count_all_purchases(self.conn), 3)
        rows = list_all_purchases(self.conn, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["supplier_name"], "B")  # mới nhất trước
        stats = {s["name"]: s for s in list_suppliers(self.conn)}
        self.assertEqual(stats["A"]["so_phieu"], 2)
        self.assertEqual(stats["A"]["tong_tien"], 200)
        self.assertEqual(stats["B"]["tong_tien"], 999)
        self.assertEqual(len(list_purchases_for_supplier(self.conn, a["id"])), 2)

    def test_soft_delete_purchase_updates_stats(self):
        s = add_supplier(self.conn, "C")
        p = add_purchase(self.conn, s["id"], [{"sp": "X", "sl": 1, "price": 10}], 10)
        soft_delete_purchase(self.conn, p["id"], by="admin")
        self.assertEqual(count_all_purchases(self.conn), 0)
        self.assertEqual(list_purchases_for_supplier(self.conn, s["id"]), [])
        row = get_purchase(self.conn, p["id"])  # row còn (xoá mềm)
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(row["deleted_by"], "admin")
        self.assertEqual(list_suppliers(self.conn)[0]["so_phieu"], 0)


class PurchasePayments(unittest.TestCase):
    """Trả tiền NCC từ két — thêm/gỡ payment + chặn trả quá phần còn nợ."""

    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "test.db")
        self.conn = get_connection(self.db)
        s = add_supplier(self.conn, "NCC K")
        self.p = add_purchase(self.conn, s["id"], [{"sp": "X", "sl": 10, "price": 10000}], 100000)

    def tearDown(self):
        self.conn.close()

    def test_pay_partial_then_full(self):
        rec, err = add_purchase_payment(self.conn, self.p["id"], 60000, "user:trang", "trang")
        self.assertEqual(err, "")
        self.assertEqual(rec["amount"], 60000)
        row = get_purchase(self.conn, self.p["id"])
        self.assertEqual(row["paid"], 60000)
        rec2, err2 = add_purchase_payment(self.conn, self.p["id"], 40000, "user:duy", "duy")
        self.assertEqual(err2, "")
        self.assertNotEqual(rec["id"], rec2["id"])
        self.assertEqual(get_purchase(self.conn, self.p["id"])["paid"], 100000)

    def test_chan_tra_qua_phan_con_no(self):
        add_purchase_payment(self.conn, self.p["id"], 90000, "user:trang", "trang")
        rec, err = add_purchase_payment(self.conn, self.p["id"], 20000, "user:trang", "trang")
        self.assertIsNone(rec)
        self.assertIn("còn nợ", err)

    def test_khong_tra_phieu_da_xoa(self):
        soft_delete_purchase(self.conn, self.p["id"])
        rec, err = add_purchase_payment(self.conn, self.p["id"], 1000, "user:duy", "duy")
        self.assertIsNone(rec)
        self.assertIn("Không tìm thấy", err)

    def test_go_payment(self):
        rec, _ = add_purchase_payment(self.conn, self.p["id"], 50000, "user:trang", "trang")
        removed = delete_purchase_payment(self.conn, self.p["id"], rec["id"])
        self.assertEqual(removed["amount"], 50000)
        self.assertEqual(get_purchase(self.conn, self.p["id"])["paid"], 0)
        self.assertIsNone(delete_purchase_payment(self.conn, self.p["id"], rec["id"]))

    def test_payments_for_cashbox_bo_phieu_xoa(self):
        add_purchase_payment(self.conn, self.p["id"], 30000, "user:trang", "trang")
        rows = payments_for_cashbox(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["supplier_name"], "NCC K")
        self.assertEqual(rows[0]["payments"][0]["amount"], 30000)
        soft_delete_purchase(self.conn, self.p["id"])
        self.assertEqual(payments_for_cashbox(self.conn), [])

    def test_sua_tong_khong_duoc_thap_hon_da_tra(self):
        add_purchase_payment(self.conn, self.p["id"], 80000, "user:trang", "trang")
        ok, err = update_purchase_items(self.conn, self.p["id"],
                                        [{"sp": "X", "sl": 1, "price": 50000}], 50000, "")
        self.assertFalse(ok)
        self.assertIn("đã trả", err)
        ok, err = update_purchase_items(self.conn, self.p["id"],
                                        [{"sp": "X", "sl": 1, "price": 80000}], 80000, "")
        self.assertTrue(ok)
        self.assertEqual(get_purchase(self.conn, self.p["id"])["remaining"], 0)

    def test_chan_doi_ncc_khi_da_tra(self):
        s2 = add_supplier(self.conn, "NCC M")
        add_purchase_payment(self.conn, self.p["id"], 30000, "user:trang", "trang")
        ok, err = update_purchase_items(self.conn, self.p["id"],
                                        [{"sp": "X", "sl": 10, "price": 10000}], 100000, "",
                                        supplier_id=s2["id"])
        self.assertFalse(ok)
        self.assertIn("nhà cung cấp", err)
        # NCC không đổi
        self.assertNotEqual(get_purchase(self.conn, self.p["id"])["supplier_id"], s2["id"])

    def test_so_tien_khong_hop_le(self):
        rec, err = add_purchase_payment(self.conn, self.p["id"], 0, "user:duy", "duy")
        self.assertIsNone(rec)
        rec, err = add_purchase_payment(self.conn, self.p["id"], -5, "user:duy", "duy")
        self.assertIsNone(rec)


if __name__ == "__main__":
    unittest.main()
