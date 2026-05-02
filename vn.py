"""vn.py — Vietnamese text normalization (shared between server + donhang_db)."""
import unicodedata

_VIET_TO_LATIN = str.maketrans(
    'ăâêôơưđĂÂÊÔƠƯĐ',
    'aaeooudAAEOOUD',
)


def vn_normalize(text: str) -> str:
    """Collapse Vietnamese text to plain Latin, lowercase, accent-insensitive.

    'cửa' -> 'cua', 'của' -> 'cua', 'cưa' -> 'cua', 'Đường' -> 'duong'.
    Maps ă â ê ô ơ ư đ → plain Latin, then strips combining tone marks.
    """
    if not text:
        return ""
    text = text.translate(_VIET_TO_LATIN)
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if not unicodedata.combining(c)).lower()
