from __future__ import annotations

import os


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    if raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


__all__ = ["read_float_env"]
