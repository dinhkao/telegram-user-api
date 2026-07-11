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


# ── Lương CHỐT THEO PHIẾU (luong_1sp) — snapshot khi gán SP, giữ khi gán lại ──

@pytest.fixture()
def slip_conn(tmp_path):
    from utils.db import get_connection
    from product_store import create_products_table, migrate_products_table, upsert_product
    from product_store.schema import _invalidate_products_cache
    from production_store.schema import create_production_table, migrate_production_table
    c = get_connection(str(tmp_path / "t.db"))
    _invalidate_products_cache()
    create_products_table(c)
    migrate_products_table(c)
    create_production_table(c)
    migrate_production_table(c)
    upsert_product(c, "K10LT", name="Kẹo 10")
    upsert_product(c, "KE", name="Kẹo E")
    yield c
    c.close()


def test_set_sp_snapshots_wage(slip_conn):
    from production_store.queries import get_slip, set_sp, set_slip_wage, upsert_slip
    c = slip_conn
    upsert_slip(c, 1, date_code="20260711")
    set_sp(c, 1, "K10LT", 3, 1200)
    assert get_slip(c, 1)["luong_1sp"] == 1200        # chốt từ bảng lương (seed)

    # bảng lương đổi SAU đó → phiếu GIỮ giá chốt
    wages.set_wage(c, "K10LT", 1500)
    assert get_slip(c, 1)["luong_1sp"] == 1200

    # văn phòng sửa tay → gán lại ĐÚNG SP cũ không mất giá sửa
    set_slip_wage(c, 1, 1300)
    set_sp(c, 1, "K10LT", 3, 1200)
    assert get_slip(c, 1)["luong_1sp"] == 1300

    # ĐỔI SP khác → chốt lại theo bảng lương của SP mới (KE seed = 500)
    set_sp(c, 1, "KE", 6, None)
    assert get_slip(c, 1)["luong_1sp"] == 500

    # SP không có trong bảng lương → NULL (theo bảng lương hiện tại khi tính)
    set_sp(c, 1, "KHONGCO", None, None)
    assert get_slip(c, 1)["luong_1sp"] is None


def test_migrate_backfills_slip_wage(slip_conn):
    from production_store.queries import get_slip, upsert_slip
    from production_store.schema import migrate_production_table
    c = slip_conn
    pid = c.execute("SELECT id FROM products WHERE code='K10LT'").fetchone()["id"]
    upsert_slip(c, 2, date_code="20260711", sp_name="K10LT", product_id=pid)
    assert get_slip(c, 2)["luong_1sp"] is None
    migrate_production_table(c)   # backfill boot
    assert get_slip(c, 2)["luong_1sp"] == 1200
