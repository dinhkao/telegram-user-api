"""Nhận diện khách hàng từ text đơn (patterns của customers) — ưu tiên khớp ở ĐẦU text."""
from __future__ import annotations
import json
import re as _re

from vn import vn_normalize

from .search import _CUSTOMER_PATTERNS_TTL, _customer_patterns_cache

_IGNORED_EXACT_PATTERNS = {"liền", "chiều"}


def _match_pattern(norm_p: str, norm_text: str):
    """Lần khớp SỚM NHẤT của 1 pattern → (kind, pos, end, score).

    kind 0 = khớp trọn từ (điểm ×10), 1 = lọt giữa chữ (×3). Khớp trọn từ luôn
    được ưu tiên hơn dù nằm sau — chữ lọt giữa từ khác là khớp yếu.
    """
    m = _re.compile(r"(?:(?<=^)|(?<=\s))" + _re.escape(norm_p) + r"(?=$|\s)", _re.IGNORECASE).search(norm_text)
    if m:
        return 0, m.start(), m.end(), len(norm_p) * 10
    pos = norm_text.find(norm_p)
    if pos >= 0:
        return 1, pos, pos + len(norm_p), len(norm_p) * 3
    return None


def _load_patterns(conn) -> list[dict]:
    import time

    now_ts = time.monotonic()
    if _customer_patterns_cache["data"] is not None and (now_ts - _customer_patterns_cache["ts"]) < _CUSTOMER_PATTERNS_TTL:
        return _customer_patterns_cache["data"]
    out = []
    cur = conn.execute("SELECT firebase_key, json FROM customers WHERE json_extract(json, '$.patterns') IS NOT NULL AND json_extract(json, '$.patterns') != '[]' AND deleted_at IS NULL")
    for row in cur.fetchall():
        cust = json.loads(row["json"])
        pats = cust.get("patterns") or []
        if pats:
            out.append({"customerID": row["firebase_key"], "customerName": cust.get("name", "N/A"), "patterns": pats})
    _customer_patterns_cache["data"], _customer_patterns_cache["ts"] = out, now_ts
    return out


def detect_customer_free_text(conn, text: str, *, _patterns=None) -> dict:
    if not text or not text.strip():
        return {"matches": [], "autoAssign": None}
    norm_text = vn_normalize(text)
    candidates_raw = _patterns if _patterns is not None else _load_patterns(conn)

    candidates = []
    for c in candidates_raw:
        best = None
        for pattern in c["patterns"]:
            p = (pattern or "").strip()
            if not p:
                continue
            # Hai từ phổ thông này gây gán nhầm khách quá thường xuyên. Chỉ bỏ
            # đúng pattern có dấu; cụm dài hơn và bản không dấu vẫn được xét.
            if p.casefold() in _IGNORED_EXACT_PATTERNS:
                continue
            hit = _match_pattern(vn_normalize(p), norm_text)
            if hit is None:
                continue
            kind, pos, end, score = hit
            # Trong CÙNG 1 khách: lấy lần khớp sớm nhất (chất lượng khớp trước).
            if best is None or (kind, pos, -score) < (best[0], best[1], -best[3]):
                best = (kind, pos, end, score, p)
        if best:
            candidates.append({
                "customerID": c["customerID"], "customerName": c["customerName"],
                "score": best[3], "bestMatchedPattern": best[4],
                "_kind": best[0], "_pos": best[1], "_end": best[2],
            })

    if not candidates:
        return {"matches": [], "autoAssign": None}

    # ƯU TIÊN ĐẦU TEXT: khách nào được nhắc SỚM NHẤT là khách của đơn. Tên xuất
    # hiện phía sau (ghi chú, địa chỉ, người nhận hộ...) không tranh nữa.
    candidates.sort(key=lambda c: (c["_kind"], c["_pos"], -c["score"]))
    first = candidates[0]
    # Chỉ những khách khớp TRÙNG CHỖ với match đầu tiên mới được coi là tranh
    # chấp (vd "liền" ⊂ "chị liền") — khi đó pattern dài hơn thắng.
    rivals = [c for c in candidates
              if c["_kind"] == first["_kind"] and c["_pos"] < first["_end"] and c["_end"] > first["_pos"]]
    rivals.sort(key=lambda c: -c["score"])
    winner = rivals[0]

    auto_assign = None
    if winner["score"] >= 20:
        if len(rivals) == 1:
            auto_assign = winner
        else:
            second = rivals[1]
            if winner["score"] >= 30 or (winner["score"] - second["score"] >= 15):
                auto_assign = winner

    ordered = rivals + [c for c in candidates if c not in rivals]
    matches = [{k: v for k, v in c.items() if not k.startswith("_")} for c in ordered]
    auto = {k: v for k, v in auto_assign.items() if not k.startswith("_")} if auto_assign else None
    return {"matches": matches, "autoAssign": auto}
