"""Nguồn gốc đơn giá từng dòng hoá đơn (order_store.price_origin)."""
from order_store.price_origin import carry_over, decide_origin

NOW = "2026-09-25T00:00:00+00:00"


def test_new_order_all_lines_need_stamp_except_zero_price():
    new = [{"sp": "K2L", "price": 16000}, {"sp": "X", "price": 0}]
    assert carry_over([], new) == [0]


def test_unchanged_price_keeps_old_origin_even_if_text_edited():
    old = [{"sp": "K2L", "sp_id": 1, "price": 16000, "price_src": "manual", "price_by": "Trinh", "price_at": "a"}]
    new = [{"sp": "K2L", "sp_id": 1, "price": 16000, "sl": 200}]
    assert carry_over(old, new) == []
    assert new[0]["price_by"] == "Trinh" and new[0]["price_src"] == "manual"


def test_changed_price_drops_old_origin_and_needs_stamp():
    old = [{"sp": "K2L", "sp_id": 1, "price": 16000, "price_src": "last", "price_from": 5}]
    new = [{"sp": "K2L", "sp_id": 1, "price": 15000, "price_src": "last", "price_from": 5}]
    assert carry_over(old, new) == [0]
    assert "price_src" not in new[0]


def test_legacy_line_without_origin_same_price_stays_unknown():
    old = [{"sp": "K2L", "price": 16000}]
    new = [{"sp": "K2L", "price": 16000}]
    assert carry_over(old, new) == []
    assert "price_src" not in new[0]


def test_duplicate_code_lines_matched_one_to_one():
    old = [{"sp": "A", "price": 10, "price_src": "list"}]
    new = [{"sp": "A", "price": 10}, {"sp": "A", "price": 10}]
    assert carry_over(old, new) == [1]
    assert new[0]["price_src"] == "list"


def test_decide_last_then_list_then_manual():
    last = {"price": 16000, "thread_id": 519000, "date": "20/09"}
    assert decide_origin(16000, last, 17000, "Duy", NOW) == {
        "price_src": "last", "price_from": 519000, "price_from_date": "20/09", "price_at": NOW}
    assert decide_origin(17000, last, 17000, "Duy", NOW)["price_src"] == "list"
    d = decide_origin(15500, last, 17000, "Duy", NOW)
    assert d["price_src"] == "manual" and d["price_by"] == "Duy"


# ── Tích hợp qua đúng choke point _save_order ─────────────────────────────
import json  # noqa: E402

from order_store.mutation_audit import reset_actor, set_actor  # noqa: E402
from order_store.serialization import _save_order, get_order_by_thread_id  # noqa: E402
from tests.test_last_prices import KH, _add_order, _conn, _item  # noqa: E402
from order_store.last_prices import invalidate_last_price_cache  # noqa: E402
from product_store.schema import _invalidate_products_cache  # noqa: E402


def _setup():
    c = _conn()
    _invalidate_products_cache()
    invalidate_last_price_cache()
    c.execute("INSERT INTO products(id, code, name) VALUES (1, 'SP1', 'SP một')")
    c.execute("INSERT INTO products(id, code, name) VALUES (2, 'SP2', 'SP hai')")
    c.execute("INSERT INTO products(id, code, name) VALUES (3, 'SP3', 'SP ba')")
    c.execute("INSERT INTO customers(firebase_key, json) VALUES (?, ?)",
              (KH, json.dumps({"name": "Khách A", "personal_price_list": {"SP2": 30000}})))
    c.execute("CREATE TABLE web_users (username TEXT PRIMARY KEY, display_name TEXT)")
    c.execute("INSERT INTO web_users VALUES ('duy', 'Duy')")
    _add_order(c, 100, "2026-09-20T10:00:00", [_item("SP1", 16000, sp_id=1)])
    _add_order(c, 200, "2026-09-25T10:00:00", [])
    return c


def test_save_order_stamps_origin_and_keeps_it_on_text_edit():
    c = _setup()
    tok = set_actor("web_user", "duy")
    try:
        order = get_order_by_thread_id(c, 200)
        order["invoice"] = [_item("SP1", 16000, sp_id=1), _item("SP2", 30000, sp_id=2), _item("SP3", 9000, sp_id=3)]
        assert _save_order(c, 200, order)
        inv = get_order_by_thread_id(c, 200)["invoice"]
        assert inv[0]["price_src"] == "last" and inv[0]["price_from"] == 100 and inv[0]["price_from_date"] == "20/09"
        assert inv[1]["price_src"] == "list"
        assert inv[2]["price_src"] == "manual" and inv[2]["price_by"] == "Duy"
    finally:
        reset_actor(tok)
    # Người khác sửa text (giá không đổi) → vẫn ghi Duy đã nhập giá SP3
    tok = set_actor("web_user", "trinh")
    try:
        order = get_order_by_thread_id(c, 200)
        order["text"] = "sửa chữ"
        order["invoice"] = [{k: v for k, v in it.items() if not k.startswith("price_") or k == "price"} for it in order["invoice"]]
        assert _save_order(c, 200, order)
        inv = get_order_by_thread_id(c, 200)["invoice"]
        assert inv[2]["price_by"] == "Duy"
        # Đổi giá SP3 → người mới
        order = get_order_by_thread_id(c, 200)
        order["invoice"][2]["price"] = 9500
        assert _save_order(c, 200, order)
        assert get_order_by_thread_id(c, 200)["invoice"][2]["price_by"] == "trinh"
    finally:
        reset_actor(tok)
