"""Unit test cho server_app/order_diff — diff trước/sau của đơn (thuần, không IO)."""
from server_app.order_diff import diff_changes, is_order_mutation


def _find(changes, label):
    return [c for c in changes if c["label"] == label]


def test_is_order_mutation():
    assert is_order_mutation("POST", "/api/order/invoice/update")
    assert is_order_mutation("POST", "/api/order/123/task_status/clear")
    assert is_order_mutation("POST", "/api/order/-100/task_status/clear")
    assert is_order_mutation("POST", "/api/order/123/custom-task")
    assert is_order_mutation("DELETE", "/api/order/123")
    assert not is_order_mutation("POST", "/api/order/reply")          # read-only
    assert not is_order_mutation("POST", "/api/order/preview")
    assert not is_order_mutation("GET", "/api/order/invoice/update")  # không phải POST


def test_scalar_money_and_customer():
    before = {"customer_name": "A", "vat": 1000, "discount": 0}
    after = {"customer_name": "B", "vat": 2000, "discount": 0}
    ch = diff_changes(before, after)
    assert _find(ch, "Khách hàng")[0] == {"label": "Khách hàng", "old": "A", "new": "B"}
    assert _find(ch, "VAT")[0]["old"] == "1.000đ"
    assert _find(ch, "VAT")[0]["new"] == "2.000đ"
    assert not _find(ch, "Giảm giá")  # không đổi → không log


def test_invoice_line_items():
    before = {"invoice": [{"sp": "K2L", "sl": 10, "price": 50000}]}
    after = {"invoice": [{"sp": "K2L", "sl": 12, "price": 55000},
                         {"sp": "NEW", "sl": 3, "price": 20000}]}
    ch = diff_changes(before, after)
    assert _find(ch, "SP K2L — số lượng")[0] == {"label": "SP K2L — số lượng", "old": "10 cây", "new": "12 cây"}
    assert _find(ch, "SP K2L — giá")[0]["new"] == "55.000đ"
    assert _find(ch, "SP NEW")[0]["old"] == "(thêm)"


def test_invoice_removed():
    before = {"invoice": [{"sp": "K2L", "sl": 10, "price": 50000}]}
    after = {"invoice": []}
    ch = diff_changes(before, after)
    assert _find(ch, "SP K2L")[0]["new"] == "(xóa)"


def test_payment_added():
    before = {"payments": []}
    after = {"payments": [{"id": "p1", "amount": 500000, "method": "Cash"}]}
    ch = diff_changes(before, after)
    thu = _find(ch, "Thu tiền")[0]
    assert "500.000đ" in thu["new"] and "tiền mặt" in thu["new"]


def test_task_status():
    before = {"task_status": {"soan_hang": {"done": False}}}
    after = {"task_status": {"soan_hang": {"done": True}}}
    ch = diff_changes(before, after)
    assert _find(ch, "Soạn hàng")[0] == {"label": "Soạn hàng", "old": "chưa", "new": "đã xong"}


def test_invoice_reference_image():
    ch = diff_changes({}, {"invoice_reference_image_id": 77})
    assert _find(ch, "Ảnh tham chiếu HĐ")[0] == {
        "label": "Ảnh tham chiếu HĐ", "old": "(trống)", "new": "Ảnh #77",
    }


def test_no_change():
    o = {"customer_name": "A", "vat": 1000, "invoice": [{"sp": "X", "sl": 1, "price": 1}]}
    assert diff_changes(o, dict(o)) == []


def test_none_before():
    assert diff_changes(None, {"customer_name": "A"})[0]["old"] == "(trống)"


def test_empty_to_zero_money_is_noop():
    # trống → 0đ cho VAT/PVC/Giảm giá KHÔNG phải thay đổi (bỏ nhiễu lịch sử)
    before = {"invoice": []}
    after = {"vat": 0, "pvc": 0, "discount": 0, "invoice": [{"sp": "K10", "sl": 100, "price": 18000}]}
    ch = diff_changes(before, after)
    assert _find(ch, "VAT") == [] and _find(ch, "Phụ phí (PVC)") == [] and _find(ch, "Giảm giá") == []
    assert _find(ch, "SP K10")  # thay đổi thật (thêm SP) vẫn còn


def test_empty_to_real_money_kept():
    ch = diff_changes({}, {"vat": 5000})
    assert _find(ch, "VAT")[0] == {"label": "VAT", "old": "(trống)", "new": "5.000đ"}


def test_real_money_to_zero_kept():
    ch = diff_changes({"vat": 5000}, {"vat": 0})
    assert _find(ch, "VAT")[0] == {"label": "VAT", "old": "5.000đ", "new": "0đ"}
