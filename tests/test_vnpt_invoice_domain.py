"""Test logic thuần hoá đơn nháp VNPT: validate body + prefill + cache khách."""
import pytest

from server_app.vnpt_invoice_domain import (
    build_prefill,
    normalize_body,
    updated_profile,
)


def _body(**over):
    b = {
        "buyer": {"cus_name": "Cty A", "tax_code": "3901220366", "address": "1 Lê Lợi"},
        "lines": [{"name": "Kẹo X", "unit": "bịch", "qty": 2, "price": 100000, "sp_id": 7}],
        "vat_rate": 8,
    }
    b.update(over)
    return b


def test_normalize_body_ok():
    buyer, lines, rate = normalize_body(_body())
    assert buyer["cus_name"] == "Cty A"
    assert buyer["phone"] == ""          # key thiếu thành chuỗi rỗng
    assert lines[0]["sp_id"] == 7 and lines[0]["qty"] == 2.0
    assert rate == 8


def test_normalize_body_rejects():
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[]))
    with pytest.raises(ValueError):
        normalize_body(_body(vat_rate=7))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "", "qty": 1, "price": 1}]))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "A", "qty": 0, "price": 1}]))
    with pytest.raises(ValueError):
        normalize_body(_body(lines=[{"name": "A", "qty": 1, "price": -5}]))
    with pytest.raises(ValueError):
        normalize_body(_body(buyer={}))
    # MST + tên + địa chỉ BẮT BUỘC (Duy chốt 2026-08-26)
    with pytest.raises(ValueError, match="tên đơn vị"):
        normalize_body(_body(buyer={"tax_code": "3901220366", "address": "x"}))
    with pytest.raises(ValueError, match="địa chỉ"):
        normalize_body(_body(buyer={"cus_name": "A", "tax_code": "3901220366"}))
    with pytest.raises(ValueError, match="mã số thuế"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x"}))
    with pytest.raises(ValueError, match="không hợp lệ"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": "12ab"}))
    # sai SỐ KIỂM TRA (checksum) — VNPT sẽ bỏ trống MST kiểu này trên hoá đơn
    with pytest.raises(ValueError, match="số kiểm tra"):
        normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": "0123456789"}))


def test_mst_valid_checksum():
    from server_app.vnpt_invoice_domain import mst_valid
    # 2 MST thật (Lê Trang Phát, VNPT-Vinaphone) + dạng chi nhánh -NNN
    assert mst_valid("3901220366") and mst_valid("0106869738")
    assert mst_valid("3901220366-001")
    assert not mst_valid("0123456789")
    assert not mst_valid("39012203")      # thiếu số
    assert not mst_valid("3901220366-01")


def test_normalize_body_mst_formats():
    for mst in ("3901220366", "3901220366-001", "39 0122 0366"):
        buyer, _, _ = normalize_body(_body(buyer={"cus_name": "A", "address": "x", "tax_code": mst}))
        assert buyer["tax_code"] == mst.replace(" ", "")


ORDER = {"invoice": [
    {"sp": "KD3", "sp_id": 7, "name": "Kẹo đậu 3kg", "sl": 3, "price": 390000},
    {"sp": "DM450", "sp_id": 10, "name": "Đậu 450g", "sl": 10, "price": 62000},
]}


def test_prefill_no_profile_uses_order_and_catalog():
    cust = {"name": "Cty B", "address": "1 Lê Lợi", "contactNumber": "090", "kh_id": 55}
    p = build_prefill(ORDER, cust, {7: "bịch", 10: "hũ"})
    assert p["buyer"]["cus_name"] == "Cty B"
    assert p["buyer"]["cus_code"] == "55"
    assert p["vat_rate"] == 8
    assert p["lines"][0] == {"name": "Kẹo đậu 3kg", "unit": "bịch", "qty": 3.0,
                             "price": 390000, "sp_id": 7}


def test_prefill_profile_overrides_name_unit_price_keeps_qty():
    cust = {
        "name": "Cty B",
        "vnpt_profile": {
            "buyer": {"cus_name": "CÔNG TY TNHH B", "tax_code": "0123"},
            "vat_rate": 10,
            "products": {"7": {"name": "Kẹo đậu phộng loại 1", "unit": "túi", "price": 400000}},
            "extra_lines": [{"name": "Phí giao", "unit": "lần", "qty": 1, "price": 30000}],
        },
    }
    p = build_prefill(ORDER, cust, {7: "bịch", 10: "hũ"})
    assert p["vat_rate"] == 10
    assert p["buyer"]["cus_name"] == "CÔNG TY TNHH B"
    ln = p["lines"][0]
    assert ln["name"] == "Kẹo đậu phộng loại 1" and ln["unit"] == "túi"
    assert ln["price"] == 400000
    assert ln["qty"] == 3.0                      # SL luôn theo ĐƠN hiện tại
    assert p["lines"][1]["name"] == "Đậu 450g"   # SP chưa có template → theo đơn
    assert p["lines"][2]["name"] == "Phí giao"   # dòng thêm tay lần trước quay lại


def test_updated_profile_merges_products_replaces_extras():
    old = {"products": {"9": {"name": "Cũ", "unit": "kg", "price": 1}},
           "extra_lines": [{"name": "Cũ extra", "qty": 2, "price": 5}]}
    buyer = {"cus_name": "X"}
    lines = [
        {"name": "Kẹo mới", "unit": "túi", "qty": 3, "price": 400000, "sp_id": 7},
        {"name": "Phí giao", "unit": "lần", "qty": 1, "price": 30000},
    ]
    prof = updated_profile(old, buyer, lines, 10)
    assert prof["products"]["9"]["name"] == "Cũ"          # giữ template SP cũ
    assert prof["products"]["7"]["price"] == 400000
    assert prof["extra_lines"] == [{"name": "Phí giao", "unit": "lần",
                                    "price": 30000, "qty": 1.0}]
    assert prof["vat_rate"] == 10 and prof["buyer"] == buyer
