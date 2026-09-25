"""Push khi tạo thanh toán (server_app.payment_notify.build_payment_notifs)."""
from server_app.payment_notify import build_payment_notifs


def test_single_payment_format():
    out = build_payment_notifs("Duy", [{"thread_id": 5, "amount": 1500000, "text": "Mỹ st\nC đặt 200 hủ"}])
    assert out == [("💰 Duy nhận 1.500.000đ", "Mỹ st", 5)]


def test_few_orders_one_push_each():
    items = [{"thread_id": i, "amount": 100000 * i, "text": f"đơn {i}"} for i in (1, 2, 3)]
    out = build_payment_notifs("Trang", items)
    assert [t for t, _, _ in out] == ["💰 Trang nhận 100.000đ", "💰 Trang nhận 200.000đ", "💰 Trang nhận 300.000đ"]


def test_many_orders_single_summary():
    items = [{"thread_id": i, "amount": 1000, "text": "x"} for i in range(1, 6)]
    assert build_payment_notifs("Duy", items, "Chị Mỹ") == [("💰 Duy nhận 5.000đ", "5 đơn của Chị Mỹ", 1)]


def test_empty_text_and_zero_amount():
    assert build_payment_notifs("Duy", [{"thread_id": 9, "amount": 20000, "text": ""}])[0][1] == "Đơn #9"
    assert build_payment_notifs("Duy", [{"thread_id": 9, "amount": 0, "text": "x"}]) == []
