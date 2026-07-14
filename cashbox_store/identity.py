"""Danh tính két — hợp nhất Telegram id ↔ web username thành 1 khoá két (THUẦN).

`by`/`createdBy` trong blob đơn là không gian trộn: Telegram id số (lệnh topic,
bot DM) hoặc web username ("tri", "duy"). Cùng 1 người phải về CÙNG 1 két:
map tg-id → username bằng cách fold dấu tên trong bot_core.config.USER_NAMES
("Trí" → "tri") khớp với web_users.username. Không IO — caller (service) nạp
web_users + USER_NAMES rồi gọi build_canon. Kết nối: cashbox_store.domain/service.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Callable

# Két đặc biệt (khoá cố định, không phải người)
BOX_NAMES = {
    "office": "Két văn phòng",
    "debt": "Két khách nợ",
    "bank": "Két ngân hàng",
    "unknown": "Két chưa rõ",
}
SPECIAL_KEYS = tuple(BOX_NAMES)


def fold(s: str) -> str:
    """Bỏ dấu tiếng Việt + thường hoá: 'Trí' → 'tri', 'Thảo' → 'thao'."""
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def box_display(key: str, names: dict[str, str] | None = None) -> str:
    """Khoá két → tên hiển thị. names = {khoá: tên} bổ sung từ build_canon."""
    if key in BOX_NAMES:
        return BOX_NAMES[key]
    if names and key in names:
        return names[key]
    if key.startswith("user:"):
        return key[5:]
    if key.startswith("tg:"):
        return f"TG {key[3:]}"
    return key


def build_canon(web_users: dict[str, str], tg_names: dict[str, str],
                extra_tg_map: dict[str, str] | None = None):
    """Tạo (canon, names): canon(by) → khoá két của người đó; names = tên hiển thị.

    - web_users: {username: display_name} (username thường, không toàn số)
    - tg_names:  {str(tg_id): tên} (bot_core.config.USER_NAMES)
    - extra_tg_map: {str(tg_id): username} ép tay (env), thắng auto-match
    Trả về canon: Any → str khoá két ("user:tri" | "tg:123" | "unknown").
    """
    by_folded = {fold(disp) or u: u for u, disp in web_users.items()}
    for u in web_users:  # username tự khớp chính nó
        by_folded.setdefault(u, u)
    tg_map: dict[str, str] = {}
    for tid, name in (tg_names or {}).items():
        u = by_folded.get(fold(name))
        if u:
            tg_map[str(tid)] = u
    for tid, u in (extra_tg_map or {}).items():
        if u in web_users:
            tg_map[str(tid)] = u

    names: dict[str, str] = {f"user:{u}": (disp or u) for u, disp in web_users.items()}
    for tid, name in (tg_names or {}).items():
        if str(tid) not in tg_map:
            names[f"tg:{tid}"] = name

    def canon(by: Any) -> str:
        if by is None:
            return "unknown"
        s = str(by).strip()
        if not s or s.upper() == "API":
            return "unknown"
        if s.isdigit():
            u = tg_map.get(s)
            return f"user:{u}" if u else f"tg:{s}"
        u = s.lower()
        if u in web_users:
            return f"user:{u}"
        # username cũ (user bị đổi tên) — bắc cầu qua fold tên hiển thị, cùng mức
        # tin cậy với nhánh tg-id ("tri" cũ → display "Trí" → username mới)
        bridged = by_folded.get(fold(s))
        if bridged:
            return f"user:{bridged}"
        # username lạ thật sự — tách két riêng để không lẫn tiền
        names.setdefault(f"user:{u}", s)
        return f"user:{u}"

    return canon, names
