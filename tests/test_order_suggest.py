"""Xếp hạng gợi ý ô tìm dashboard Đơn (server_app/order_suggest_routes)."""
from server_app.order_suggest_routes import rank_customers, rank_products


def test_customers_name_match_first_then_recent_order():
    rows = [  # đã sắp mua-gần-nhất trước
        {"key": "1", "name": "Chị Hoa chợ Lớn"},      # tên không khớp (khớp qua mẫu nhận diện)
        {"key": "2", "name": "Tạp hoá Loan"},          # từ bắt đầu bằng
        {"key": "3", "name": "Loan Phú"},              # bắt đầu bằng
        {"key": "4", "name": "Loan"},                  # trùng hẳn
    ]
    out = rank_customers("loan", rows)
    assert [r["key"] for r in out] == ["4", "3", "2", "1"]


def test_customers_limit_and_stable():
    rows = [{"key": str(i), "name": f"Loan {i}"} for i in range(10)]
    out = rank_customers("loan", rows, limit=3)
    assert [r["key"] for r in out] == ["0", "1", "2"]


def test_products_code_before_name_and_skip_not_sellable():
    prods = [
        {"code": "BD", "name": "Bánh dừa K2L"},
        {"code": "K2L-1", "name": "Kẹo lạc 1"},
        {"code": "K2L", "name": "Kẹo lạc"},
        {"code": "NLK2L", "name": "Nguyên liệu", "can_sell": False},
    ]
    out = rank_products("k2l", prods)
    assert [p["code"] for p in out] == ["K2L", "K2L-1", "BD"]


def test_products_name_without_accents():
    prods = [{"code": "A1", "name": "Kẹo dừa"}, {"code": "A2", "name": "Mè xửng"}]
    assert [p["code"] for p in rank_products("keo dua", prods)] == ["A1"]


def test_products_name_prefix_beats_code_substring():
    prods = [{"code": "BANH8P", "name": "Bánh 8 phần"}, {"code": "X1", "name": "Anh đào"}]
    assert [p["code"] for p in rank_products("an", prods)] == ["X1", "BANH8P"]


def test_products_all_words_anywhere():
    prods = [{"code": "KDD", "name": "Kẹo đậu phộng dừa sấy"}, {"code": "KM", "name": "Kẹo mè"}]
    assert [p["code"] for p in rank_products("keo dua", prods)] == ["KDD"]
