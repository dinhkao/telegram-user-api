from __future__ import annotations
import json
import re as _re

from vn import vn_normalize

from .search import _CUSTOMER_PATTERNS_TTL, _customer_patterns_cache


def detect_customer_free_text(conn, text: str, *, _patterns=None) -> dict:
    if not text or not text.strip():
        return {"matches": [], "autoAssign": None}
    norm_text = vn_normalize(text)
    if _patterns is not None:
        candidates_raw = _patterns
    else:
        import time

        now_ts = time.monotonic()
        if _customer_patterns_cache["data"] is not None and (now_ts - _customer_patterns_cache["ts"]) < _CUSTOMER_PATTERNS_TTL:
            candidates_raw = _customer_patterns_cache["data"]
        else:
            candidates_raw = []
            cur = conn.execute("SELECT firebase_key, json FROM customers WHERE json_extract(json, '$.patterns') IS NOT NULL AND json_extract(json, '$.patterns') != '[]' AND deleted_at IS NULL")
            for row in cur.fetchall():
                cust = json.loads(row["json"])
                pats = cust.get("patterns") or []
                if pats:
                    candidates_raw.append({"customerID": row["firebase_key"], "customerName": cust.get("name", "N/A"), "patterns": pats})
            _customer_patterns_cache["data"], _customer_patterns_cache["ts"] = candidates_raw, now_ts
    candidates = []
    for c in candidates_raw:
        best_pattern, best_score = None, 0
        for pattern in c["patterns"]:
            p = (pattern or "").strip()
            if not p:
                continue
            norm_p = vn_normalize(p)
            if _re.compile(r"(?:^|\s)" + _re.escape(norm_p) + r"(?:$|\s)", _re.IGNORECASE).search(norm_text):
                score = len(norm_p) * 10
                if score > best_score:
                    best_score, best_pattern = score, p
            elif norm_p in norm_text:
                score = len(norm_p) * 3
                if score > best_score:
                    best_score, best_pattern = score, p
        if best_pattern:
            candidates.append({"customerID": c["customerID"], "customerName": c["customerName"], "score": best_score, "bestMatchedPattern": best_pattern})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    auto_assign = None
    if candidates and candidates[0]["score"] >= 20:
        if len(candidates) == 1:
            auto_assign = candidates[0]
        else:
            top, second = candidates[0], candidates[1]
            if top["score"] >= 30 or (top["score"] - second["score"] >= 15):
                auto_assign = top
    return {"matches": candidates, "autoAssign": auto_assign}
