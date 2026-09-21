"""Cache tên khách của dashboard lợi nhuận phải TƯƠI theo thời gian, không dính
theo id(connection) (địa chỉ được cấp lại → map đóng băng suốt đời process)."""
import gc
import json
import os
import sqlite3
import tempfile

import profit_dashboard.utils as U


def _db():
    db = os.path.join(tempfile.mkdtemp(), "t.db")
    s = sqlite3.connect(db)
    s.execute("CREATE TABLE customers (firebase_key TEXT, json TEXT, deleted_at TEXT)")
    s.execute("INSERT INTO customers VALUES ('k1', ?, NULL)", (json.dumps({"name": "Chị Lan"}),))
    s.commit(); s.close()
    return db


def _reset():
    U._NAME_CACHE = None


def test_new_customer_visible_after_ttl_across_new_connections(monkeypatch):
    _reset()
    db = _db()
    ids = set()
    for _ in range(3):   # nhiều request = nhiều connection mở/đóng — id thường trùng
        c = sqlite3.connect(db); ids.add(id(c))
        assert U.resolve_customer_name(c, {"khach_hang_id": "k1"}) == "Chị Lan"
        c.close(); del c; gc.collect()
    s = sqlite3.connect(db)
    s.execute("INSERT INTO customers VALUES ('k2', ?, NULL)", (json.dumps({"name": "Anh Tâm"}),))
    s.execute("UPDATE customers SET json=? WHERE firebase_key='k1'", (json.dumps({"name": "Chị Lan mới"}),))
    s.commit(); s.close()
    # Hết TTL → map dựng lại, connection MỚI (kể cả trùng id) thấy khách mới + tên mới
    monkeypatch.setattr(U.time, "monotonic", lambda: U._NAME_CACHE[0] + U._NAME_TTL + 1)
    c = sqlite3.connect(db)
    assert U.resolve_customer_name(c, {"khach_hang_id": "k2"}) == "Anh Tâm"
    assert U.resolve_customer_name(c, {"khach_hang_id": "k1"}) == "Chị Lan mới"
    c.close()


def test_within_ttl_reuses_map_without_requery():
    _reset()
    db = _db()
    c = sqlite3.connect(db)
    assert U.resolve_customer_name(c, {"khach_hang_id": "k1"}) == "Chị Lan"
    built = U._NAME_CACHE
    U.resolve_customer_name(c, {"khach_hang_id": "k1"})
    assert U._NAME_CACHE is built
    c.close()


def test_denormalized_name_wins_over_map():
    _reset()
    c = sqlite3.connect(":memory:")
    assert U.resolve_customer_name(c, {"customer_name": "Trực tiếp", "khach_hang_id": "x"}) == "Trực tiếp"
    assert U.resolve_customer_name(c, {"khach_hang": {"name": "Dict"}}) == "Dict"
