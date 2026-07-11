"""Bảng lương SP DB-backed (production_store.wages) — seed, upsert, xoá khi luong<=0."""
import sqlite3

import pytest

from production_store import wages


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT, name TEXT)")
    wages.ensure_table(c)
    yield c
    c.close()


def test_seed_and_list(conn):
    rows = {w["code"]: w for w in wages.list_wages(conn)}
    assert rows["K2NT"]["luong"] == 420
    assert rows["K2NT128"]["luong"] == 420
    # seed idempotent — gọi lại không nhân đôi / không ghi đè
    conn.execute("UPDATE production_wages SET luong = 999 WHERE code = 'K2NT'")
    wages.ensure_table(conn)
    rows = {w["code"]: w for w in wages.list_wages(conn)}
    assert rows["K2NT"]["luong"] == 999 and len([c for c in rows if c == "K2NT"]) == 1


def test_set_wage_upsert_and_delete(conn):
    wages.set_wage(conn, "abC1", 555, by="duy")   # thường → IN HOA
    rows = {w["code"]: w for w in wages.list_wages(conn)}
    assert rows["ABC1"]["luong"] == 555 and rows["ABC1"]["updated_by"] == "duy"
    wages.set_wage(conn, "ABC1", 600, by="trang")
    assert {w["code"]: w for w in wages.list_wages(conn)}["ABC1"]["luong"] == 600
    # luong <= 0 → xoá entry (về missing_wage)
    wages.set_wage(conn, "ABC1", 0)
    assert "ABC1" not in {w["code"] for w in wages.list_wages(conn)}
    with pytest.raises(ValueError):
        wages.set_wage(conn, "  ", 100)


def test_wage_per_cay_reads_cache(monkeypatch):
    monkeypatch.setattr(wages, "_cache", {"K9": {"luong": 777}})
    assert wages.wage_per_cay("k9") == 777
    assert wages.wage_per_cay("K404") == 0
    assert wages.has_wage("K9") and not wages.has_wage("K404")
