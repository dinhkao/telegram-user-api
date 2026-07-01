"""Tiny assertion harness shared by the sheets_bot.parse test modules."""

from __future__ import annotations

FAILS: list[str] = []


def check(name, cond):
    if cond:
        print(f"  ok: {name}")
    else:
        print(f"  FAIL: {name}")
        FAILS.append(name)


def run(module_tests):
    for fn in module_tests:
        print(f"\n{fn.__module__}.{fn.__name__}:")
        fn()
