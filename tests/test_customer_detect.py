from order_store.customer_detect import detect_customer_free_text


def _patterns(*patterns: str) -> list[dict]:
    return [{
        "customerID": "customer-1",
        "customerName": "Khách 1",
        "patterns": list(patterns),
    }]


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
