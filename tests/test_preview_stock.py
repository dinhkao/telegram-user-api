"""Preview tạo đơn trả kèm tồn kho từng mã (server_app.order_api_auto._preview_stock)."""
import inventory_store.stock_lookup as sl
from server_app.order_api_auto import _preview_stock


def test_preview_stock_dedup_and_missing(monkeypatch):
    calls = []

    def fake(conn, code):
        calls.append(code)
        if code == "K2L":
            return {"code": "K2L", "unit": "cây", "stock": 247, "boxes": 6,
                    "display": {"name": "Thùng", "qty": 4.9}}
        if code == "BOOM":
            raise RuntimeError("no table")
        return None

    monkeypatch.setattr(sl, "stock_by_code", fake)
    out = _preview_stock(None, [{"sp": "k2l"}, {"sp": "K2L "}, {"sp": "LP"}, {"sp": "BOOM"}, {"sp": ""}])
    assert calls == ["K2L", "LP", "BOOM"]           # mã lặp tra 1 lần, mã rỗng bỏ qua
    assert out["K2L"] == {"stock": 247, "unit": "cây", "display": {"name": "Thùng", "qty": 4.9}}
    assert out["LP"] is None and out["BOOM"] is None  # không có mã / lỗi kho → không hiện
