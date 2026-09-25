"""NGUỒN GỐC ĐƠN GIÁ từng dòng hoá đơn — gắn tại choke point `_save_order`.

Mỗi dòng có giá MỚI/ĐỔI so với lần lưu trước được đóng dấu:
- `price_src="last"` + `price_from` (thread_id) + `price_from_date` ('dd/mm'): giá
  TRÙNG giá khách mua lần gần nhất ở ĐƠN KHÁC (parser tự lấy — order_store.last_prices);
- `price_src="list"`: trùng bảng giá của khách;
- `price_src="manual"` + `price_by`: người lưu tự nhập (gõ trong text / sửa tay).
Kèm `price_at` (ISO UTC). Dòng giá KHÔNG đổi giữ nguyên dấu cũ (sửa text đơn không
làm đổi người đã nhập giá). Dòng cũ chưa có dấu (đơn trước tính năng) mà giá không
đổi → để trống, không đoán. Giá 0 → xoá dấu. Luật thuần: `carry_over`/`decide_origin`
(tests/test_price_origin.py). Nối: order_store.last_prices, order_store.search,
order_store.mutation_audit (người đang thao tác), web_users, bot_core.config.USER_NAMES.
"""
from __future__ import annotations

from datetime import UTC, datetime

FIELDS = ("price_src", "price_from", "price_from_date", "price_by", "price_at")


def _key(it: dict):
    return ("id", it["sp_id"]) if it.get("sp_id") is not None else ("sp", str(it.get("sp") or "").upper().strip())


def _price(it: dict) -> int:
    try:
        return int(float(it.get("price") or 0))
    except (TypeError, ValueError):
        return 0


def carry_over(old_inv: list, new_inv: list) -> list[int]:
    """THUẦN, sửa tại chỗ `new_inv`: dòng nào khớp 1 dòng cũ (cùng SP + cùng giá) thì
    chép dấu nguồn của dòng cũ (dòng cũ không có dấu → xoá dấu, giữ 'chưa rõ').
    Trả index các dòng CẦN đóng dấu mới (giá mới/đổi, giá > 0)."""
    pool: dict = {}
    for it in old_inv or []:
        if isinstance(it, dict):
            pool.setdefault((_key(it), _price(it)), []).append(it)
    need = []
    for i, it in enumerate(new_inv or []):
        if not isinstance(it, dict):
            continue
        p = _price(it)
        cands = pool.get((_key(it), p))
        if cands:
            old = cands.pop(0)
            for f in FIELDS:
                if f in old:
                    it[f] = old[f]
                else:
                    it.pop(f, None)
            continue
        for f in FIELDS:
            it.pop(f, None)
        if p > 0:
            need.append(i)
    return need


def decide_origin(price: int, last: dict | None, list_price: int | None, actor: str, now: str) -> dict:
    """THUẦN: dấu nguồn cho 1 dòng giá mới. last = {price, thread_id, date} của đơn khác."""
    if last and int(last.get("price") or 0) == price:
        return {"price_src": "last", "price_from": last.get("thread_id"),
                "price_from_date": last.get("date") or "", "price_at": now}
    if list_price and int(list_price) == price:
        return {"price_src": "list", "price_at": now}
    return {"price_src": "manual", "price_by": actor or "", "price_at": now}


def _actor_name(conn, order: dict) -> str:
    from .mutation_audit import _actor_ctx
    typ, aid = _actor_ctx.get()
    if typ == "web_user":
        try:
            row = conn.execute("SELECT display_name FROM web_users WHERE username = ?", (str(aid).lower(),)).fetchone()
            if row and row[0]:
                return str(row[0])
        except Exception:  # noqa: BLE001 — DB test không có web_users
            pass
        return str(aid)
    if typ == "telegram":
        try:
            from bot_core.config import USER_NAMES
            return USER_NAMES.get(str(aid), str(aid))
        except Exception:  # noqa: BLE001
            return str(aid)
    # Hệ thống (auto-parse đơn đăng từ Telegram…) → giá gõ trong text là của người tạo đơn
    return str(order.get("created_by") or "")


def stamp_price_origin(conn, thread_id: int, before: dict | None, after: dict) -> None:
    """Đóng dấu nguồn giá vào after['invoice'] (sửa tại chỗ). Best-effort: lỗi thì bỏ qua."""
    inv = after.get("invoice")
    if not isinstance(inv, list) or not inv:
        return
    need = carry_over((before or {}).get("invoice") or [], inv)
    if not need:
        return
    kh = after.get("khach_hang_id") or after.get("khID")
    last, plist = {}, {}
    if kh:
        from .last_prices import last_price_sources
        last = last_price_sources(conn, kh, exclude_thread=thread_id)
        try:
            from .search import get_customer_price_list
            plist = get_customer_price_list(conn, kh)
        except Exception:  # noqa: BLE001
            plist = {}
    actor = _actor_name(conn, after)
    now = datetime.now(UTC).isoformat()
    for i in need:
        it = inv[i]
        code = str(it.get("sp") or "").upper().strip()
        it.update(decide_origin(_price(it), last.get(code), plist.get(code), actor, now))
