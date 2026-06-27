from __future__ import annotations

from datetime import datetime, timedelta, timezone

_ACCENT_MAP = str.maketrans(
    "àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    "ÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ",
    "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
    "AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYYD",
)


def esc(s: str) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_money(n) -> str:
    return f"{int(n or 0):,}đ"


def to_k(n) -> str:
    n = int(n or 0)
    return f"{'-' if n < 0 else ''}{round(abs(n) / 1000):,}k"


def vn_dt(value):
    try:
        if not value:
            return None
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc) if value > 1e10 else datetime.fromtimestamp(value, tz=timezone.utc)
    except Exception:
        return None


def vn_str(value, fmt: str) -> str:
    dt = vn_dt(value)
    return dt.astimezone(timezone(timedelta(hours=7))).strftime(fmt) if dt else ""


def accentless_lower(text: str) -> str:
    return str(text or "").lower().translate(_ACCENT_MAP)


def internal_group_id(group_id: int) -> str:
    group_id_str = str(group_id)
    return group_id_str[4:] if group_id_str.startswith("-100") else str(abs(group_id))


def qr_url(data: str, size: int = 64, safe: str = "/") -> str:
    if not data:
        return ""
    import urllib.parse
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={urllib.parse.quote(data, safe=safe)}"


def vn_now():
    return datetime.now(timezone(timedelta(hours=7)))
