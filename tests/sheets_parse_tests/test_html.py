"""HTML export builder tests (grouping, integer totals, escaping)."""

from __future__ import annotations

from sheets_bot import parse

from .harness import check


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


def test_build_html_escaping():
    header = ["Tên", "STT"]
    row = ["<b>&'\"", "1"]
    html = parse.build_html("d", [header, row])
    check("html escapes < and &", "&lt;b&gt;&amp;" in html)


TESTS = [test_build_html, test_build_html_escaping]
