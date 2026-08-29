from order_store.customer_detect import detect_customer_free_text


def _patterns(*patterns: str) -> list[dict]:
    return [{
        "customerID": "customer-1",
        "customerName": "Khách 1",
        "patterns": list(patterns),
    }]


def _cust(cid: str, *patterns: str) -> dict:
    return {"customerID": cid, "customerName": f"Khách {cid}", "patterns": list(patterns)}


def test_ignores_exact_lien_and_chieu_patterns():
    result = detect_customer_free_text(
        None,
        "Liền chiều K10 5",
        _patterns=_patterns("liền", "chiều"),
    )

    assert result == {"matches": [], "autoAssign": None}


def test_still_matches_longer_and_unaccented_patterns():
    longer = detect_customer_free_text(
        None,
        "giao chị liền K10 5",
        _patterns=_patterns("chị liền"),
    )
    unaccented = detect_customer_free_text(
        None,
        "giao lien K10 5",
        _patterns=_patterns("lien"),
    )

    assert longer["autoAssign"]["bestMatchedPattern"] == "chị liền"
    assert unaccented["autoAssign"]["bestMatchedPattern"] == "lien"


def test_khach_o_dau_text_thang_du_ten_sau_dai_hon():
    # "cô Hường Bình Tân" dài hơn nhưng nằm ở ghi chú cuối → không tranh với
    # khách được nhắc ngay đầu đơn.
    result = detect_customer_free_text(
        None,
        "anh Tuấn K10 5 T15 2, giao giùm cô Hường Bình Tân",
        _patterns=[_cust("A", "anh tuấn"), _cust("B", "cô Hường Bình Tân")],
    )

    assert result["autoAssign"]["customerID"] == "A"
    assert [m["customerID"] for m in result["matches"]] == ["A", "B"]


def test_van_uu_tien_pattern_dai_hon_khi_trung_cho():
    # Hai khách khớp CÙNG chỗ ở đầu text → pattern dài hơn thắng như cũ.
    result = detect_customer_free_text(
        None,
        "chị liền K10 5",
        _patterns=[_cust("A", "chị liền"), _cust("B", "liền")],
    )

    assert result["autoAssign"]["customerID"] == "A"


def test_khop_tron_tu_thang_khop_lot_giua_chu_du_nam_sau():
    # "khoa" chỉ lọt giữa chữ "khoai" ở đầu text → không được ưu tiên hơn tên
    # khớp trọn từ nằm sau.
    result = detect_customer_free_text(
        None,
        "khoai môn 5 giao chị Hoa",
        _patterns=[_cust("A", "khoa"), _cust("B", "chị Hoa")],
    )

    assert result["autoAssign"]["customerID"] == "B"
