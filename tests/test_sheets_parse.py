"""Runner for the sheets_bot.parse unit tests (PURE functions).

Run: PYTHONPATH=. .venv/bin/python tests/test_sheets_parse.py

Test cases live in tests/sheets_parse_tests/, one module per concern.
"""

from __future__ import annotations

import sys

from tests.sheets_parse_tests import (
    harness,
    test_dates_payload,
    test_gviz_export,
    test_html,
    test_schema,
)


def main():
    for module in (test_schema, test_dates_payload, test_gviz_export, test_html):
        harness.run(module.TESTS)

    print("\n" + "=" * 40)
    if harness.FAILS:
        print(f"FAILED ({len(harness.FAILS)}): {harness.FAILS}")
        sys.exit(1)
    print("ALL PARSE TESTS PASSED")


if __name__ == "__main__":
    main()
