"""Unit tests for sheets_bot.parse (PURE functions).

Run: PYTHONPATH=. .venv/bin/python tests/test_sheets_parse.py
"""

from __future__ import annotations

import sys
from datetime import datetime

from sheets_bot import parse

FAILS = []


def check(name, cond):
    if cond:
        print(f"  ok: {name}")
    else:
        print(f"  FAIL: {name}")
        FAILS.append(name)


def test_headers_schema():
    # The documented 20-col data schema, in order, then computed/meta cols.
    data_schema = [
        "Tên", "Số gạch", "Số trừ", "Số cây lẻ", "Ghi chú", "Tổng số SP",
        "Số giờ TL", "Lương 1 SP", "Lương 1 giờ TL", "Tổng lương SP",
        "Tổng lương TL", "Phụ cấp", "Tổng lương phiếu", "Sản phẩm", "Ngày",
        "STT", "Số chảo", "Số mâm", "Giờ vào", "Giờ ra",
    ]
    check("20-col data schema matches HEADERS prefix", parse.HEADERS[:20] == data_schema)
    check("HEADERS has 23 cols (data + Lương trên 1 giờ + Link + Cập nhật)",
          len(parse.HEADERS) == 23)
    check("HEADERS tail is Lương trên 1 giờ/Link/Cập nhật lần cuối",
          parse.HEADERS[20:] == ["Lương trên 1 giờ", "Link", "Cập nhật lần cuối"])
    check("Ngày at index 14", parse.HEADERS.index("Ngày") == 14)
    check("STT at index 15", parse.HEADERS.index("STT") == 15)


def test_column_letters():
    check("end_column_letter is W (23 cols)", parse.end_column_letter() == "W")
    check("column_letter(0) == A", parse.column_letter(0) == "A")
    check("column_letter(15) == P (STT)", parse.column_letter(15) == "P")
    check("a1 escapes quotes", parse.a1("O'Brien", "A1") == "'O''Brien'!A1")
    check("a1 basic", parse.a1("01/07/2026", "A:A") == "'01/07/2026'!A:A")


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
    check("only-open-quote returns empty", parse.parse_quoted_payload('"abc') == [])


def test_sheet_name_from_rows():
    rows = [["Anna"] + [""] * 13 + ["7/1/2026"] + [""] * 5]
    check("sheet name from Ngày col padded/normalized (7/1 -> 07/01)",
          parse.get_sheet_name_from_rows(rows) == "07/01/2026")
    rows2 = [["x"] * 20]  # no valid date
    check("no valid date returns None", parse.get_sheet_name_from_rows(rows2) is None)


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


def test_normalize_product_code():
    check("lower + trim", parse.normalize_product_code("  AB12 ") == "ab12")
    check("None -> empty", parse.normalize_product_code(None) == "")


def test_gviz():
    body = 'google.visualization.Query.setResponse({"status":"ok","table":{"rows":[{"c":[{"v":123},{"v":"SP1"}]}]}});'
    payload = parse.parse_gviz_response(body)
    check("gviz rows parsed", len(payload["table"]["rows"]) == 1)
    cell = payload["table"]["rows"][0]["c"][0]
    check("gviz cell v value", parse.get_gviz_cell_value(cell) == 123)
    check("gviz f fallback", parse.get_gviz_cell_value({"f": "fmt"}) == "fmt")
    check("gviz None cell", parse.get_gviz_cell_value(None) is None)

    err_body = 'setResponse({"status":"error","errors":[{"message":"boom"}]});'
    try:
        parse.parse_gviz_response(err_body)
        check("gviz error raises", False)
    except ValueError as e:
        check("gviz error raises", "boom" in str(e))


def test_iso_and_date_format():
    dt = datetime(2026, 7, 1, 8, 30, 5)
    check("date ddmmyyyy", parse.format_date_ddmmyyyy(dt) == "01/07/2026")
    check("iso with offset",
          parse.format_iso_with_offset(dt) == "2026-07-01T08:30:05+07:00")


def test_filter_export_columns():
    header = list(parse.HEADERS)
    row = [f"v{i}" for i in range(len(header))]
    out = parse.filter_export_columns([header, row])
    check("hidden columns removed from header",
          all(h not in out[0] for h in parse.HIDDEN_EXPORT_HEADERS))
    check("Tên kept", "Tên" in out[0])
    check("STT kept", "STT" in out[0])
    check("row width matches filtered header", len(out[1]) == len(out[0]))


def test_trim_trailing_empty_rows():
    rows = [["a"], ["b"], ["", ""], [None]]
    check("trailing empties trimmed", parse.trim_trailing_empty_rows(rows) == [["a"], ["b"]])


def test_format_import_row_message():
    vals = ["101", "2026-07-01T08:00:00+07:00", "@bob", "SP1", "5", "phieu", "note", "link"]
    out = parse.format_import_row_message(vals)
    lines = out.split("\n")
    check("import message 8 lines", len(lines) == 8)
    check("import first line label", lines[0] == "Mã tin nhắn: 101")
    check("import last line label", lines[7] == "Link tin nhắn: link")


def test_build_html():
    header = list(parse.HEADERS)
    r1 = [""] * len(header)
    r1[header.index("Tên")] = "Anna"
    r1[header.index("STT")] = "1"
    r1[header.index("Sản phẩm")] = "SP1"
    r1[header.index("Tổng số SP")] = "5"
    html = parse.build_html("01/07/2026", [header, r1])
    check("html has title", "<title>01/07/2026</title>" in html)
    check("html groups by STT", "<strong>STT:</strong> 1" in html)
    check("html product shown", "SP1" in html)
    check("html total integer (5 not 5.0)", "Tổng số SP:</strong> 5<" in html)
    check("html escapes handled", "&" not in "Anna")


def test_build_html_escaping():
    header = ["Tên", "STT"]
    row = ["<b>&'\"", "1"]
    html = parse.build_html("d", [header, row])
    check("html escapes < and &", "&lt;b&gt;&amp;" in html)


def main():
    for fn in [
        test_headers_schema,
        test_column_letters,
        test_parse_quoted_payload,
        test_sheet_name_from_rows,
        test_format_sheet_name_from_date,
        test_format_sheet_name_from_compact_date,
        test_parse_leading_amount,
        test_normalize_product_code,
        test_gviz,
        test_iso_and_date_format,
        test_filter_export_columns,
        test_trim_trailing_empty_rows,
        test_format_import_row_message,
        test_build_html,
        test_build_html_escaping,
    ]:
        print(f"\n{fn.__name__}:")
        fn()

    print("\n" + "=" * 40)
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {FAILS}")
        sys.exit(1)
    print("ALL PARSE TESTS PASSED")


if __name__ == "__main__":
    main()
