from server_app.order_api_mutations import _stock_locked_price_update


def _order():
    return {
        "invoice": [
            {"sp": "SP-A", "sl": 2, "price": 100, "note": "x", "cost_price": 40},
            {"sp": "SP-B", "sl": 1, "price": 200, "cost_price": 80},
        ],
        "discount": 10,
        "pvc": 20,
        "vat": 30,
    }


def test_stock_locked_order_allows_price_note_and_preserves_metadata():
    invoice = [
        {"sp": "sp-a", "sl": 2, "price": 150, "note": "đổi ghi chú"},
        {"sp": "SP-B", "sl": 1, "price": 250, "note": ""},
    ]
    result = _stock_locked_price_update(_order(), invoice, {"discount": 15, "pvc": 25, "vat": 30})
    assert [row["price"] for row in result] == [150, 250]
    assert [row["note"] for row in result] == ["đổi ghi chú", ""]
    assert [row["cost_price"] for row in result] == [40, 80]


def test_stock_locked_order_allows_vat_change():
    # Chốt kho chỉ khoá mã hàng + SL — VAT (và CK/PVC) đổi thoải mái (áp ở caller).
    base = [
        {"sp": "SP-A", "sl": 2, "price": 150, "note": "x"},
        {"sp": "SP-B", "sl": 1, "price": 250, "note": ""},
    ]
    assert _stock_locked_price_update(_order(), base, {"vat": 31}) is not None
    assert _stock_locked_price_update(_order(), base, {"vat": 0}) is not None


def test_stock_locked_order_rejects_line_changes():
    base = [
        {"sp": "SP-A", "sl": 2, "price": 150, "note": "x"},
        {"sp": "SP-B", "sl": 1, "price": 250, "note": ""},
    ]
    changed_quantity = [{**base[0], "sl": 3}, base[1]]
    assert _stock_locked_price_update(_order(), changed_quantity, {}) is None       # đổi SL
    changed_code = [{**base[0], "sp": "SP-C"}, base[1]]
    assert _stock_locked_price_update(_order(), changed_code, {}) is None           # đổi mã
    assert _stock_locked_price_update(_order(), base[:-1], {}) is None              # xoá dòng
    added = base + [{"sp": "SP-C", "sl": 1, "price": 50, "note": ""}]
    assert _stock_locked_price_update(_order(), added, {}) is None                  # thêm dòng
    assert _stock_locked_price_update(_order(), base, {"discount": 11, "pvc": 21}) is not None
