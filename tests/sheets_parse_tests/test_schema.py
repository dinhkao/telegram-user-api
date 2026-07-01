"""Header schema and A1/column helper tests."""

from __future__ import annotations

from sheets_bot import parse

from .harness import check


def test_headers_schema():
    data_schema = [
        "Tên", "Số gạch", "Số trừ", "Số cây lẻ", "Ghi chú", "Tổng số SP",
        "Số giờ TL", "Lương 1 SP", "Lương 1 giờ TL", "Tổng lương SP",
        "Tổng lương TL", "Phụ cấp", "Tổng lương phiếu", "Sản phẩm", "Ngày",
        "STT", "Số chảo", "Số mâm", "Giờ vào", "Giờ ra",
    ]
    check("20-col data schema matches HEADERS prefix", parse.HEADERS[:20] == data_schema)
    check("HEADERS has 23 cols", len(parse.HEADERS) == 23)
    check("HEADERS tail Lương trên 1 giờ/Link/Cập nhật",
          parse.HEADERS[20:] == ["Lương trên 1 giờ", "Link", "Cập nhật lần cuối"])
    check("Ngày at index 14", parse.HEADERS.index("Ngày") == 14)
    check("STT at index 15", parse.HEADERS.index("STT") == 15)


def test_column_letters():
    check("end_column_letter is W (23 cols)", parse.end_column_letter() == "W")
    check("column_letter(0) == A", parse.column_letter(0) == "A")
    check("column_letter(15) == P (STT)", parse.column_letter(15) == "P")
    check("a1 escapes quotes", parse.a1("O'Brien", "A1") == "'O''Brien'!A1")
    check("a1 basic", parse.a1("01/07/2026", "A:A") == "'01/07/2026'!A:A")


def test_header_helpers():
    check("headers_match exact", parse.headers_match(parse.HEADERS, parse.HEADERS))
    check("headers_match length mismatch", not parse.headers_match(["Tên"], parse.HEADERS))
    check("normalize_header_cell trims", parse.normalize_header_cell("  STT ") == "STT")
    check("contains_all_headers true",
          parse.contains_all_headers(parse.HEADERS, parse.MANAGED_HEADER_MARKERS))
    check("contains_all_headers false",
          not parse.contains_all_headers(["Tên"], parse.MANAGED_HEADER_MARKERS))


TESTS = [test_headers_schema, test_column_letters, test_header_helpers]
