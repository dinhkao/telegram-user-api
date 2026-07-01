"""Date parsing, payload parsing, product codes, and ISO formatting tests."""

from __future__ import annotations

from datetime import datetime

from sheets_bot import parse

from .harness import check


def test_parse_quoted_payload():
    raw = '"Anna;5;0;0;note;5;;;;;;;;SP1;01/07/2026;1;2;3;08:00;17:00"'
    rows = parse.parse_quoted_payload(raw)
    check("single row parsed", len(rows) == 1)
    check("row has 20 cells", len(rows[0]) == 20)
    check("first cell Anna", rows[0][0] == "Anna")
    check("date cell", rows[0][14] == "01/07/2026")
    check("stt cell", rows[0][15] == "1")
    multi = '"a;1;2\nb;3;4\n\n  c;5;6  "'
    mrows = parse.parse_quoted_payload(multi)
    check("blank lines dropped", len(mrows) == 3)
    check("cells trimmed", mrows[2] == ["c", "5", "6"])
    check("non-quoted returns empty", parse.parse_quoted_payload("hello") == [])
    check("only-open-quote empty", parse.parse_quoted_payload('"abc') == [])


def test_sheet_name_from_rows():
    rows = [["Anna"] + [""] * 13 + ["7/1/2026"] + [""] * 5]
    check("sheet name from Ngày col (7/1 -> 07/01)",
          parse.get_sheet_name_from_rows(rows) == "07/01/2026")
    check("no valid date returns None", parse.get_sheet_name_from_rows([["x"] * 20]) is None)


def test_format_sheet_name_from_date():
    check("slash 2-digit year -> 20xx",
          parse.format_sheet_name_from_date("1/7/26") == "01/07/2026")
    check("dash separator", parse.format_sheet_name_from_date("01-07-2026") == "01/07/2026")
    check("already padded", parse.format_sheet_name_from_date("15/12/2025") == "15/12/2025")
    check("garbage None", parse.format_sheet_name_from_date("hello") is None)
    check("3-digit year rejected", parse.format_sheet_name_from_date("1/7/203") is None)


def test_format_sheet_name_from_compact_date():
    check("DDMMYYYY -> DD/MM/YYYY",
          parse.format_sheet_name_from_compact_date("01072026") == "01/07/2026")
    check("wrong length None", parse.format_sheet_name_from_compact_date("1072026") is None)
    check("non-digit None", parse.format_sheet_name_from_compact_date("0107202a") is None)


def test_parse_leading_amount():
    check("int amount + note",
          parse.parse_leading_amount("50 gạch men") == {"amount": 50.0, "note": "gạch men"})
    check("decimal comma", parse.parse_leading_amount("3,5")["amount"] == 3.5)
    check("negative", parse.parse_leading_amount("-2 abc")["amount"] == -2.0)
    check("no leading number None", parse.parse_leading_amount("abc 5") is None)
    check("empty None", parse.parse_leading_amount("") is None)
    check("bare number empty note", parse.parse_leading_amount("10")["note"] == "")


def test_misc():
    check("lower + trim", parse.normalize_product_code("  AB12 ") == "ab12")
    check("None -> empty", parse.normalize_product_code(None) == "")
    dt = datetime(2026, 7, 1, 8, 30, 5)
    check("date ddmmyyyy", parse.format_date_ddmmyyyy(dt) == "01/07/2026")
    check("iso with offset", parse.format_iso_with_offset(dt) == "2026-07-01T08:30:05+07:00")


TESTS = [
    test_parse_quoted_payload,
    test_sheet_name_from_rows,
    test_format_sheet_name_from_date,
    test_format_sheet_name_from_compact_date,
    test_parse_leading_amount,
    test_misc,
]
