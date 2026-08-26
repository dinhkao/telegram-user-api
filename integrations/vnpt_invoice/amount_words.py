"""Đọc số tiền VND thành chữ tiếng Việt (cho ô AmountInWords của HĐĐT).

Thuần, không IO — unit-tested ở tests/test_vnpt_invoice.py.
"""
from __future__ import annotations

_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_GROUPS = ["", " nghìn", " triệu", " tỷ", " nghìn tỷ", " triệu tỷ"]


def _read_triple(n: int, has_higher: bool) -> str:
    """Đọc 1 nhóm 3 chữ số (0–999). has_higher = có nhóm lớn hơn đứng trước
    (để đọc 'không trăm lẻ...' cho đúng, vd 1.005 = 'một nghìn không trăm lẻ năm')."""
    tram, chuc, dv = n // 100, (n // 10) % 10, n % 10
    parts: list[str] = []
    if tram or has_higher:
        parts.append(f"{_DIGITS[tram]} trăm")
    if chuc == 0:
        if dv and (tram or has_higher):
            parts.append("lẻ")
        if dv:
            parts.append(_DIGITS[dv])
    elif chuc == 1:
        parts.append("mười")
        if dv == 5:
            parts.append("lăm")
        elif dv:
            parts.append(_DIGITS[dv])
    else:
        parts.append(f"{_DIGITS[chuc]} mươi")
        if dv == 1:
            parts.append("mốt")
        elif dv == 5:
            parts.append("lăm")
        elif dv:
            parts.append(_DIGITS[dv])
    return " ".join(parts)


def amount_to_words(amount: int) -> str:
    """1234000 → 'Một triệu hai trăm ba mươi bốn nghìn đồng chẵn'."""
    n = int(amount)
    if n < 0:
        raise ValueError("số tiền âm")
    if n == 0:
        return "Không đồng"
    triples: list[int] = []
    while n > 0:
        triples.append(n % 1000)
        n //= 1000
    if len(triples) > len(_GROUPS):
        raise ValueError("số tiền quá lớn")
    parts: list[str] = []
    for idx in range(len(triples) - 1, -1, -1):
        t = triples[idx]
        if t == 0:
            continue
        has_higher = idx != len(triples) - 1
        parts.append(_read_triple(t, has_higher) + _GROUPS[idx])
    words = " ".join(parts)
    words = words[0].upper() + words[1:]
    return f"{words} đồng chẵn"
