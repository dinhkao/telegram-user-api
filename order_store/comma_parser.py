from __future__ import annotations
import re

from .search import get_customer_price_list

_RE_NO_QC = re.compile(r"^\s*([A-Za-z0-9-]+)\s{2,}(\d+(?:\.\d+)?)(?:\s+(\d+(?:\.\d+)?))?(?:\s+(.+))?\s*$")
_RE_QC_T = re.compile(r"^\d+t$")
_RE_QC_B = re.compile(r"^\d+b$")
_RE_QC_TB = re.compile(r"^([\d.]+)t([\d.]+)b$")
_RE_QC_TX_BX = re.compile(r"^(t\d+|b\d+)$")


def _parse_no_qc(line: str) -> dict | None:
    m = _RE_NO_QC.match(line)
    if not m:
        return None
    return {"sp": m.group(1), "sl1qc": m.group(2), "price": m.group(3), "note": m.group(4)}


def _parse_qc(qc: str) -> tuple[str | None, list[int]]:
    if not qc:
        return None, [1]
    if _RE_QC_T.match(qc):
        return "t", [int(qc[:-1])]
    if _RE_QC_B.match(qc):
        return "b", [int(qc[:-1])]
    m = _RE_QC_TB.match(qc)
    if m:
        return "tb", [int(m.group(1)), int(m.group(2))]
    if _RE_QC_TX_BX.match(qc):
        return qc, [1]
    return None, [1]


def parse_comma_text(text: str, conn, kh_id: str | int | None) -> list[dict]:
    cleaned = text.replace(",", "").strip()
    price_list = get_customer_price_list(conn, kh_id) if kh_id else {}
    lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
    while lines and lines[-1].lower().replace(" ", "") in ("taohd", "taohoadon"):
        lines.pop()
    invoice = []
    for line in lines:
        clean_line = re.sub(r"<[^>]+>$", "", line).strip()
        if not clean_line:
            continue
        no_qc = _parse_no_qc(clean_line)
        if no_qc:
            sp, sl1qc_val, price_override, note, qc_type, so_qc = no_qc["sp"].upper(), float(no_qc["sl1qc"]), no_qc["price"], no_qc["note"], None, [1]
        else:
            words = clean_line.split()
            if len(words) < 2:
                continue
            sp = words[0].upper()
            if not re.match(r"^[A-Z0-9][A-Z0-9.-]*$", sp):
                continue
            qc_type, so_qc = _parse_qc(words[1])
            if qc_type is not None:
                try:
                    sl1qc_val = float(words[2]) if len(words) > 2 else 0
                except (ValueError, TypeError):
                    continue
                price_override, note = (words[3] if len(words) > 3 else None), (" ".join(words[4:]) if len(words) > 4 else None)
            else:
                try:
                    sl1qc_val = float(words[1])
                except (ValueError, TypeError):
                    continue
                price_override, note = (words[2] if len(words) > 2 else None), (" ".join(words[3:]) if len(words) > 3 else None)
        price = price_list.get(sp, 0)
        if price_override is not None:
            try:
                price = int(price_override)
            except ValueError:
                note = f"{price_override} {note or ''}".strip() or None
        sl = int(sl1qc_val) if sl1qc_val else 0
        for v in so_qc:
            sl *= v
        invoice.append({"sp": sp, "so_qc": so_qc, "qc_type": qc_type, "sl1pc": sl1qc_val, "sl": sl, "price": price, "note": note})
    return invoice
