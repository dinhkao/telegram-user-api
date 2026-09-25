"""Lọc dashboard Đơn theo MÃ khách (server_app.orders_db.customer_where) — tên trùng
không lẫn; khach_hang_id lưu lẫn kiểu số/chuỗi vẫn khớp đủ."""
import json
import sqlite3

from server_app.orders_db import customer_where


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE orders (thread_id INTEGER, json TEXT, cust_key
        GENERATED ALWAYS AS (coalesce(json_extract(json, '$.khach_hang_id'),
                                      json_extract(json, '$.khID'))) VIRTUAL)""")
    rows = [(1, {"khach_hang_id": "24", "customer_name": "Hai Sóc"}),
            (2, {"khach_hang_id": 24, "customer_name": "Hai Sóc"}),
            (3, {"khID": "24"}),
            (4, {"khach_hang_id": "25697", "customer_name": "Hai Sóc"}),
            (5, {"customer_name": "Hai Sóc"})]
    c.executemany("INSERT INTO orders(thread_id, json) VALUES (?, ?)", [(t, json.dumps(j)) for t, j in rows])
    return c


def _ids(conn, key):
    w, p = customer_where(key)
    return sorted(r[0] for r in conn.execute(f"SELECT thread_id FROM orders o WHERE {w}", p))


def test_same_name_different_key_not_mixed():
    c = _conn()
    assert _ids(c, "24") == [1, 2, 3]
    assert _ids(c, "25697") == [4]


def test_non_numeric_key():
    c = _conn()
    c.execute("INSERT INTO orders(thread_id, json) VALUES (6, ?)", (json.dumps({"khach_hang_id": "abc"}),))
    assert _ids(c, "abc") == [6]
