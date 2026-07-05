"""Unit tests cho quy_store.domain (luật thuần sổ quỹ)."""
from quy_store.domain import normalize_type, parse_amount, signed, compute_summary


def test_normalize_type():
    assert normalize_type("thu") == "thu"
    assert normalize_type("THU") == "thu"
    assert normalize_type("+") == "thu"
    assert normalize_type("income") == "thu"
    assert normalize_type("chi") == "chi"
    assert normalize_type("-") == "chi"
    assert normalize_type("expense") == "chi"
    assert normalize_type("xyz") is None
    assert normalize_type("") is None
    assert normalize_type(None) is None


def test_parse_amount():
    assert parse_amount(1000) == 1000
    assert parse_amount("1000") == 1000
    assert parse_amount("1.000.000") == 1000000
    assert parse_amount("1,500") == 1500
    assert parse_amount(0) is None
    assert parse_amount(-5) is None
    assert parse_amount("abc") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount(True) is None


def test_signed():
    assert signed({"type": "thu", "amount": 500}) == 500
    assert signed({"type": "chi", "amount": 500}) == -500
    assert signed({"type": "chi", "amount": 0}) == 0


def test_compute_summary():
    rs = [
        {"type": "thu", "amount": 1000},
        {"type": "thu", "amount": 500},
        {"type": "chi", "amount": 300},
    ]
    s = compute_summary(rs)
    assert s == {"thu": 1500, "chi": 300, "balance": 1200, "count": 3}


def test_compute_summary_empty():
    assert compute_summary([]) == {"thu": 0, "chi": 0, "balance": 0, "count": 0}
