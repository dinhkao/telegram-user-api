"""Compatibility loader for the legacy order_commands_v3 implementation."""
from __future__ import annotations

from pathlib import Path


def _load_legacy() -> str:
    base = Path(__file__).with_name("command_handlers_v3") / "legacy_order_commands_v3"
    return "".join(path.read_text(encoding="utf-8") for path in sorted(base.glob("part_*.txt")))


exec(compile(_load_legacy(), __file__, "exec"))

