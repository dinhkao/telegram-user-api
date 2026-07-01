"""Google Visualization API (gviz) response parsing."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_gviz_response(body: str) -> dict:
    m = re.search(r"setResponse\((.*)\);?$", body, re.S)
    if not m:
        raise ValueError("Invalid GViz response.")
    payload = json.loads(m.group(1))
    status = payload.get("status")
    if status and status != "ok":
        errors = payload.get("errors") or []
        msg = errors[0].get("message") if errors else None
        raise ValueError(msg or "GViz query failed.")
    return payload


def get_gviz_cell_value(cell: Any) -> Any:
    if not cell:
        return None
    v = cell.get("v")
    if v is not None:
        return v
    f = cell.get("f")
    if f is not None:
        return f
    return None
