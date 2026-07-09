"""Resolve HIỂN THỊ item hoá đơn theo danh tính SP: mã (`sp`) + tên (`name`) luôn
là bản HIỆN HÀNH (sp_id → products; fallback resolve mã cho đơn chưa backfill;
SP đã xoá → giữ snapshot). GIÁ / SỐ LƯỢNG / cost_price KHÔNG BAO GIỜ đổi.
Map dịch cache 30s / process (đổi mã → tối đa 30s là mọi list tươi; render chủ
động gọi invalidate). Nối: product_store, utils.db."""
from __future__ import annotations

import time

from product_store import code_alias_map, get_all_products
from utils.db import get_connection

_cache: dict = {"data": None, "ts": 0.0}
_TTL = 30


def invalidate_display_maps() -> None:
    _cache["data"] = None
    _cache["ts"] = 0.0


def display_maps(conn=None) -> dict:
    """{by_id: {pid: product}, by_code: {MÃ: product}, alias: {MÃ_CŨ: product}}."""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return _cache["data"]
    own = conn is None
    if own:
        conn = get_connection()
    try:
        prods = get_all_products(conn)
        by_id = {int(p["id"]): p for p in prods if p.get("id") is not None}
        by_code = {str(p["code"]).upper(): p for p in prods}
        alias = {}
        for old, pid in code_alias_map(conn).items():
            if pid in by_id:
                alias[old] = by_id[pid]
    finally:
        if own:
            conn.close()
    _cache["data"] = {"by_id": by_id, "by_code": by_code, "alias": alias}
    _cache["ts"] = now
    return _cache["data"]


def display_item(maps: dict, it: dict) -> dict:
    """1 item → bản copy với sp/name hiện hành. Không nhận ra SP → giữ nguyên."""
    p = None
    sid = it.get("sp_id")
    if sid is not None:
        try:
            p = maps["by_id"].get(int(sid))
        except (TypeError, ValueError):
            p = None
    if p is None:
        code = str(it.get("sp") or "").strip().upper()
        if code:
            p = maps["by_code"].get(code) or maps["alias"].get(code)
    if not p:
        return it
    out = dict(it)
    out["sp"] = p["code"]
    name = p.get("name") or p.get("kv_full_name")
    if name:
        out["name"] = name
    return out


def resolve_invoice_display(items, conn=None) -> list:
    """List item → list bản copy hiển thị hiện hành. Blob gốc KHÔNG đổi.
    Input không phải list (blob hỏng legacy) → trả []."""
    if not isinstance(items, list) or not items:
        return items if isinstance(items, list) else []
    maps = display_maps(conn)
    return [display_item(maps, it) if isinstance(it, dict) else it for it in items]
