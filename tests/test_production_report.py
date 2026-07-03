"""Characterize the production báo cáo parser on real semicolon data.

Fixtures are the exact blocks the user pastes into the production topic
(mã SP at col 13, note at col 4, comma decimals, blank/note rows → 0).
"""
from production_store.domain import parse_report, compute_report, looks_like_report

# Real paste #1 — K10LT
BLOCK_K10LT = """Hiền;2;2;3;;24;;;;;;;;K10LT;1/7/2026;6;10;7;16:10;16:55
Lệ;;;;nghỉ;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Trọng;1;-2;3;;21;;;;;;;;K10LT;1/7/2026;6;10;6;16:10;16:55
Mai;2;2;4;;25;;;;;;;;K10LT;1/7/2026;6;10;7;16:10;16:55
Sáu;1;;3;;15;;;;;;;;K10LT;1/7/2026;6;10;4;16:10;16:55
Hằng;2;;2;;29;;;;;;;;K10LT;1/7/2026;6;10;9;16:10;16:55
Kim;;;;nghỉ;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Quyên;2;4;4;;19;;;;;;;;K10LT;1/7/2026;6;10;5;16:10;16:55
Duy;;;;vít;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Là;1;-2;3;;21;;;;;;;;K10LT;1/7/2026;6;10;6;16:10;16:55
Huệ;;;;nghỉ;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Tâm;;;;vô kẹo;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Vĩ;2;4;4;;19;;;;;;;;K10LT;1/7/2026;6;10;5;16:10;16:55
Trân;;;;;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Thủy Đặng;;;;vít;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Kim Dung;;;;Q.kẹo;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
Bảo Xuyên;;;;Q.kẹo;0;;;;;;;;K10LT;1/7/2026;6;10;0;16:10;16:55
"""

# Real paste #2 — K10LV85, includes comma decimals (3,5 / 48,5)
BLOCK_K10LV85 = """Hiền;5;;5;;77;;;;;;;;K10LV85;1/7/2026;3;20;24;08:25;10:00
Lệ;;;;nghỉ;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Trọng;4;4;3,5;;48,5;;;;;;;;K10LV85;1/7/2026;3;20;15;08:25;10:00
Mai;5;3;3;;66;;;;;;;;K10LV85;1/7/2026;3;20;21;08:25;10:00
Sáu;3;4;4;;34;;;;;;;;K10LV85;1/7/2026;3;20;10;08:25;10:00
Hằng;5;2;4;;70;;;;;;;;K10LV85;1/7/2026;3;20;22;08:25;10:00
Kim;;;;nghỉ;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Quyên;3;;4;;46;;;;;;;;K10LV85;1/7/2026;3;20;14;08:25;10:00
Duy;;;;vít;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Là;3;;4;;46;;;;;;;;K10LV85;1/7/2026;3;20;14;08:25;10:00
Huệ;4;1;3;;57;;;;;;;;K10LV85;1/7/2026;3;20;18;08:25;10:00
Tâm;;;;vô kẹo;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Vĩ;3;;3;;45;;;;;;;;K10LV85;1/7/2026;3;20;14;08:25;10:00
Trân;;;;;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Thủy Đặng;;;;vít;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Kim Dung;;;;Q.kẹo;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
Bảo Xuyên;;;;Q.kẹo;0;;;;;;;;K10LV85;1/7/2026;3;20;0;08:25;10:00
"""


def test_looks_like_report_true_on_paste():
    assert looks_like_report(BLOCK_K10LT)
    assert looks_like_report(BLOCK_K10LV85)


def test_looks_like_report_false_on_commands():
    assert not looks_like_report("5 hàng mới")
    assert not looks_like_report("SX 100")
    assert not looks_like_report("K10LV85")
    assert not looks_like_report("")


def test_parse_extracts_metadata():
    p = parse_report(BLOCK_K10LT)
    assert p["product_code"] == "K10LT"
    assert p["date"] == "1/7/2026"
    assert p["start"] == "16:10"
    assert p["end"] == "16:55"
    assert len(p["rows"]) == 17


def test_parse_comma_decimal():
    p = parse_report(BLOCK_K10LV85)
    trong = next(r for r in p["rows"] if r["name"] == "Trọng")
    assert trong["so_cay_le"] == 3.5


def test_compute_k10lt_totals():
    result = compute_report(parse_report(BLOCK_K10LT), so_cay_1_mam=3)
    assert result["product_code"] == "K10LT"
    by_name = {r["name"]: r["tong_calc"] for r in result["rows"]}
    assert by_name["Hiền"] == 24
    assert by_name["Trọng"] == 21   # negative số trừ (-2)
    assert by_name["Hằng"] == 29
    assert by_name["Lệ"] == 0       # nghỉ
    assert result["grand_total"] == 173


def test_compute_k10lv85_totals():
    result = compute_report(parse_report(BLOCK_K10LV85), so_cay_1_mam=3)
    by_name = {r["name"]: r["tong_calc"] for r in result["rows"]}
    assert by_name["Hiền"] == 77
    assert by_name["Trọng"] == 48.5  # comma decimal path
    assert by_name["Mai"] == 66
    assert by_name["Tâm"] == 0        # vô kẹo
    assert result["grand_total"] == 489.5


def test_compute_falls_back_to_sheet_total_when_no_yield():
    # product unknown → so_cay_1_mam 0 → use tổng column (idx5)
    result = compute_report(parse_report(BLOCK_K10LV85), so_cay_1_mam=0)
    by_name = {r["name"]: r["tong_calc"] for r in result["rows"]}
    assert by_name["Hiền"] == 77
    assert result["grand_total"] == 489.5
