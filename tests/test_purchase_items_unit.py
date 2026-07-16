"""Test _parse_items phiếu nhập — nhận đơn vị nhập (unit/unit_factor snapshot)."""
from server_app.purchase_routes import _parse_items


def test_item_giu_don_vi_hop_le():
    items, total = _parse_items({"items": [
        {"sp": "keo1", "sl": 3, "price": 100_000, "unit": "thùng", "unit_factor": 30},
    ]})
    assert items == [{"sp": "KEO1", "sl": 3.0, "price": 100_000.0, "unit": "thùng", "unit_factor": 30.0}]
    assert total == 300_000.0   # tổng = SL × giá theo ĐƠN VỊ ĐÃ CHỌN


def test_don_vi_xau_bi_bo_qua_khong_chan_phieu():
    # thiếu factor / factor ≤ 0 / unit rỗng → item vẫn hợp lệ, chỉ rơi phần đơn vị
    for bad in ({"unit": "thùng"}, {"unit": "thùng", "unit_factor": 0},
                {"unit": "", "unit_factor": 30}, {"unit_factor": "abc", "unit": "thùng"}):
        items, _ = _parse_items({"items": [{"sp": "A", "sl": 1, "price": 5, **bad}]})
        assert items == [{"sp": "A", "sl": 1.0, "price": 5.0}]


def test_khong_don_vi_nhu_cu():
    items, total = _parse_items({"items": [{"sp": "A", "sl": 2, "price": 10}]})
    assert items == [{"sp": "A", "sl": 2.0, "price": 10.0}] and total == 20.0
