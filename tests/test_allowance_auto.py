"""Test rule PHỤ CẤP TỰ ĐỘNG theo ghi chú báo cáo — production_store/allowance_auto."""
from production_store.allowance_auto import compute_auto_allowances


def _w(name, piece, note=""):
    return {"name": name, "piece": piece, "note": note}


def test_kim_vit_bang_cao_nhat():
    ws = [_w("Kim", 100_000, "vít kẹo"), _w("Trang", 250_000), _w("Duy", 200_000)]
    out = compute_auto_allowances(ws)
    assert out == {"Kim": 250_000}


def test_duy_vit_hoac_rac_me_bang_cao_nhi():
    ws = [_w("Duy", 100_000, "rắc mè"), _w("Trang", 250_000), _w("Kim", 200_000)]
    assert compute_auto_allowances(ws) == {"Duy": 200_000}
    ws2 = [_w("Duy", 100_000, "vít"), _w("Trang", 250_000), _w("Kim", 200_000)]
    assert compute_auto_allowances(ws2) == {"Duy": 200_000}


def test_quay_keo_theo_ten():
    ws = [_w("Kim Dung", 50_000, "quậy kẹo"), _w("Thủy Đặng", 60_000, "quậy kẹo"),
          _w("Bảo", 70_000), _w("Xuyên", 300_000)]
    out = compute_auto_allowances(ws)
    assert out["Kim Dung"] == 300_000     # cao nhất
    assert out["Thủy Đặng"] == 70_000     # cao nhì
    assert "Bảo" not in out               # có tên trong rule nhưng KHÔNG có ghi chú
    assert "Xuyên" not in out


def test_nghi_xoa_phu_cap_moi_nguoi():
    ws = [_w("Kim", 100_000, "vít kẹo nghỉ"), _w("Trang", 250_000, "nghỉ")]
    out = compute_auto_allowances(ws)
    assert out == {"Kim": 0.0, "Trang": 0.0}   # nghỉ thắng mọi rule


def test_khong_khop_ten_hoac_tu_gan_giong():
    # "Kim Dung" không ăn rule của "Kim"; "nghiêm" không phải "nghỉ"
    ws = [_w("Kim Dung", 100_000, "vít kẹo"), _w("Trang", 250_000, "làm nghiêm túc")]
    assert compute_auto_allowances(ws) == {}


def test_ten_bo_dau_khong_phan_biet_hoa_thuong():
    ws = [_w("KIM", 10, "Vít kẹo"), _w("trang", 99)]
    assert compute_auto_allowances(ws) == {"KIM": 99.0}
