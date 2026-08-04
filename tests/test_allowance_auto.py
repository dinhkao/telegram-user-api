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
          _w("Hằng", 70_000), _w("Mai", 300_000)]
    out = compute_auto_allowances(ws)
    assert out["Kim Dung"] == 300_000     # cao nhất
    assert out["Thủy Đặng"] == 70_000     # cao nhì
    assert "Hằng" not in out              # không có rule
    assert "Mai" not in out


def test_bao_xuyen_quay_keo_bang_cao_nhat():
    # Tên trong rule phải là TÊN ĐẦY ĐỦ: tách "bao"/"xuyen" thì "Bảo Xuyên" trượt hết rule
    ws = [_w("Bảo Xuyên", 0, "quậy kẹo"), _w("Hiền", 112_000), _w("Hằng", 111_000)]
    assert compute_auto_allowances(ws) == {"Bảo Xuyên": 112_000}


def test_bao_khong_an_rule_cua_bao_xuyen():
    # "Bảo" là thợ KHÁC (lương thời gian) — không được ăn rule của "Bảo Xuyên"
    ws = [_w("Bảo", 0, "quậy kẹo"), _w("Hiền", 112_000)]
    assert compute_auto_allowances(ws) == {}


def test_bao_xuyen_vit_van_bang_cao_nhat():
    # Từ 21/7 Bảo Xuyên đổi ghi chú "quậy kẹo" → "vít kẹo". HẠNG ĐI THEO NGƯỜI nên vẫn
    # cao nhất, KHÔNG tụt xuống cao nhì như Thủy Đặng dù cùng ghi "vít".
    ws = [_w("Bảo Xuyên", 0, "vít kẹo"), _w("Hiền", 125_000), _w("Hằng", 123_000)]
    assert compute_auto_allowances(ws) == {"Bảo Xuyên": 125_000}


def test_kim_dung_chi_an_quay_keo_khong_an_vit():
    # Kim Dung CHƯA BAO GIỜ ghi "vít" (0 dòng trong dữ liệu thật) → không thêm từ khoá
    # suy diễn cho cô ấy; giữ vậy để test chống-trùng-tên "Kim"/"Kim Dung" còn ý nghĩa.
    ws = [_w("Kim Dung", 100_000, "vít kẹo"), _w("Hiền", 125_000)]
    assert compute_auto_allowances(ws) == {}


def test_cung_phieu_moi_nguoi_mot_hang_theo_ten():
    # Ảnh chụp thực tế phiếu #40998: cùng ghi "vít kẹo" nhưng Bảo Xuyên hạng 0,
    # Thủy Đặng hạng 1 — bằng chứng hạng gắn với NGƯỜI chứ không phải việc.
    ws = [_w("Bảo Xuyên", 0, "vít kẹo"), _w("Thủy Đặng", 0, "vít kẹo"),
          _w("Kim Dung", 0, "quậy kẹo"), _w("Hiền", 125_000), _w("Hằng", 123_000)]
    assert compute_auto_allowances(ws) == {
        "Bảo Xuyên": 125_000, "Kim Dung": 125_000, "Thủy Đặng": 123_000}


def test_thuy_dang_vit_bang_cao_nhi():
    # Thủy Đặng ghi "vít kẹo" (không phải "quậy kẹo") → vẫn phải có phụ cấp, hạng nhì
    ws = [_w("Thủy Đặng", 0, "vít kẹo"), _w("Hiền", 112_000), _w("Hằng", 111_000)]
    assert compute_auto_allowances(ws) == {"Thủy Đặng": 111_000}


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


def _wh(name, piece, note="", hour=False):
    return {"name": name, "piece": piece, "note": note, "hour": hour}


def test_nguoi_tinh_theo_gio_khong_lam_moc():
    # Thủy Đặng nhập giờ (piece 250k) KHÔNG được làm mốc → Kim lấy theo cây cao nhất (62k)
    ws = [_wh("Thủy Đặng", 250_000, "vít kẹo", hour=True),
          _wh("Kim", 0, "vít kẹo"), _wh("Hiền", 62_000), _wh("Mai", 50_000)]
    out = compute_auto_allowances(ws)
    assert out["Kim"] == 62_000
    assert "Thủy Đặng" not in out          # tính theo giờ → không có phụ cấp


def test_nguoi_tinh_theo_gio_khong_nhan_phu_cap():
    # Kim khớp rule vít nhưng NHẬP GIỜ → không có phụ cấp
    ws = [_wh("Kim", 300_000, "vít kẹo", hour=True), _wh("Hiền", 62_000)]
    assert compute_auto_allowances(ws) == {}


def test_tam_vo_keo_bang_dung_tien_cua_trong():
    # Mốc theo TÊN, không theo hạng: Trọng chỉ đứng hạng 3 mà Tâm vẫn lấy đúng tiền
    # của anh ấy (số thật phiếu #40963: Trọng 79 cây × 1.000).
    ws = [_w("Tâm", 8_000, "vô kẹo"), _w("Hiền", 112_000), _w("Hằng", 111_000),
          _w("Mai", 107_000), _w("Trọng", 79_000)]
    assert compute_auto_allowances(ws) == {"Tâm": 79_000}


def test_tam_rac_com_dua_cung_bang_trong():
    ws = [_w("Tâm", 0, "rắc cơm dừa"), _w("Hiền", 48_070), _w("Trọng", 29_260)]
    assert compute_auto_allowances(ws) == {"Tâm": 29_260}


def test_tam_ghi_chu_khac_thi_khong_co_phu_cap():
    ws = [_w("Tâm", 50_000, "Đã -1 mâm"), _w("Trọng", 29_260)]
    assert compute_auto_allowances(ws) == {}


def test_tam_khong_ghi_gi_khi_trong_vang_mat():
    # Trọng nghỉ/không có dòng → không có mốc → KHÔNG ghi gì (giữ số văn phòng nhập tay)
    ws = [_w("Tâm", 0, "vô kẹo"), _w("Hiền", 112_000), _w("Hằng", 111_000)]
    assert compute_auto_allowances(ws) == {}


def test_tam_nghi_van_bi_xoa_phu_cap():
    ws = [_w("Tâm", 0, "vô kẹo nghỉ"), _w("Trọng", 79_000)]
    assert compute_auto_allowances(ws) == {"Tâm": 0.0}


def test_tran_khong_lam_moc():
    # Trân cao nhất nhưng bị loại khỏi mốc → Kim lấy theo người kế (Duy 90k)
    ws = [_wh("Kim", 0, "vít kẹo"), _wh("Trân", 200_000), _wh("Duy", 90_000)]
    out = compute_auto_allowances(ws)
    assert out["Kim"] == 90_000
