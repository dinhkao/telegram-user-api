"""GViz parsing, export-column filtering, and import-row message tests."""

from __future__ import annotations

from sheets_bot import parse

from .harness import check


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


def test_filter_export_columns():
    header = list(parse.HEADERS)
    row = [f"v{i}" for i in range(len(header))]
    out = parse.filter_export_columns([header, row])
    check("hidden columns removed", all(h not in out[0] for h in parse.HIDDEN_EXPORT_HEADERS))
    check("Tên kept", "Tên" in out[0])
    check("STT kept", "STT" in out[0])
    check("row width matches header", len(out[1]) == len(out[0]))


def test_trim_trailing_empty_rows():
    rows = [["a"], ["b"], ["", ""], [None]]
    check("trailing empties trimmed", parse.trim_trailing_empty_rows(rows) == [["a"], ["b"]])


def test_format_import_row_message():
    vals = ["101", "2026-07-01T08:00:00+07:00", "@bob", "SP1", "5", "phieu", "note", "link"]
    lines = parse.format_import_row_message(vals).split("\n")
    check("import message 8 lines", len(lines) == 8)
    check("import first line label", lines[0] == "Mã tin nhắn: 101")
    check("import last line label", lines[7] == "Link tin nhắn: link")


def test_refs():
    url = parse.build_sheet_row_url("SHEET", 42, 7)
    check("row url", url.endswith("edit#gid=42&range=A7"))
    check("hyperlink formula",
          parse.build_hyperlink_formula('a"b', "lbl") == '=HYPERLINK("a""b";"lbl")')


TESTS = [
    test_gviz,
    test_filter_export_columns,
    test_trim_trailing_empty_rows,
    test_format_import_row_message,
    test_refs,
]
