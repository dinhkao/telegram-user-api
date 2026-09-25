"""ĐIỀN BÙ nguồn đơn giá (order_store.price_origin) cho các đơn LƯU TRƯỚC tính năng.

Đơn cũ không biết chắc ai gõ giá → suy từ dữ liệu, đánh dấu `price_backfill: 1`:
- giá TRÙNG giá khách mua ở ĐƠN LIỀN TRƯỚC có mã đó (tạo trước đơn này) → "last" + link;
- trùng bảng giá hiện tại của khách → "list";
- còn lại → "manual" KHÔNG ghi tên (UI hiện "✎ nhập tay").
Chỉ đụng dòng CHƯA có dấu; ghi thẳng blob, KHÔNG đổi updated_at (danh sách "Mới cập
nhật" không bị xáo). MẶC ĐỊNH CHẠY THỬ — thêm --apply mới ghi; --revert gỡ dấu bù.

    .venv/bin/python tools/backfill_price_origin.py --since 2026-08-10
    .venv/bin/python tools/backfill_price_origin.py --since 2026-08-10 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from order_store.last_prices import _code_maps, _price  # noqa: E402
from order_store.price_origin import FIELDS  # noqa: E402
from order_store.search import get_customer_price_list  # noqa: E402
from utils.db import get_connection, transaction  # noqa: E402
from utils.paths import SHARED_DB_PATH  # noqa: E402


def _code(it, by_id, alias):
    code = by_id.get(it.get("sp_id")) if it.get("sp_id") is not None else None
    if not code:
        raw = str(it.get("sp") or "").upper().strip()
        code = alias.get(raw, raw)
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-10", help="đơn tạo từ ngày (YYYY-MM-DD)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true", help="gỡ mọi dấu price_backfill")
    a = ap.parse_args()
    conn = get_connection(SHARED_DB_PATH)
    rows = conn.execute(
        "SELECT thread_id, order_created, json, cust_key FROM orders WHERE deleted_at IS NULL "
        "AND cust_key IS NOT NULL ORDER BY order_created, thread_id").fetchall()
    by_id, alias = _code_maps(conn)
    plist_cache: dict = {}
    last_seen: dict = defaultdict(dict)   # khách → {mã: (giá, thread_id, 'dd/mm')} theo thứ tự thời gian
    updates, stats = [], Counter()
    for r in rows:
        try:
            j = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        kh = str(r["cust_key"])
        inv = j.get("invoice") if isinstance(j.get("invoice"), list) else []
        created = str(r["order_created"] or "")
        changed = False
        if a.revert:
            for it in inv:
                if isinstance(it, dict) and it.get("price_backfill"):
                    for f in (*FIELDS, "price_backfill"):
                        it.pop(f, None)
                    changed = True
        elif created[:10] >= a.since:
            if kh not in plist_cache:
                plist_cache[kh] = get_customer_price_list(conn, kh)
            for it in inv:
                if not isinstance(it, dict) or it.get("price_src"):
                    continue
                p = _price(it.get("price"))
                if not p:
                    continue
                code = _code(it, by_id, alias)
                prev = last_seen[kh].get(code)
                if prev and prev[0] == p:
                    it.update({"price_src": "last", "price_from": prev[1], "price_from_date": prev[2]})
                elif plist_cache[kh].get(code) == p:
                    it["price_src"] = "list"
                else:
                    it["price_src"] = "manual"
                it["price_backfill"] = 1
                stats[it["price_src"]] += 1
                changed = True
        if changed:
            updates.append((json.dumps(j, ensure_ascii=False), r["thread_id"], r["json"]))
        # ghi nhận giá của đơn này cho các đơn SAU (mỗi mã: lần đầu trong đơn)
        date = f"{created[8:10]}/{created[5:7]}" if len(created) >= 10 else ""
        seen = set()
        for it in inv:
            if not isinstance(it, dict):
                continue
            code, p = _code(it, by_id, alias), _price(it.get("price"))
            if code and p and code not in seen:
                last_seen[kh][code] = (p, r["thread_id"], date)
                seen.add(code)
    print(f"đơn cần ghi: {len(updates)} · dòng: {dict(stats)}" if not a.revert else f"đơn gỡ dấu: {len(updates)}")
    if not a.apply:
        print("CHẠY THỬ — thêm --apply để ghi")
        return
    # Chỉ ghi khi blob CHƯA đổi kể từ lúc đọc (server đang chạy có thể vừa sửa đơn đó)
    n = 0
    with transaction(conn):
        for new, tid, old in updates:
            n += conn.execute("UPDATE orders SET json = ? WHERE thread_id = ? AND json = ?", (new, tid, old)).rowcount
    print(f"đã ghi {n}/{len(updates)} đơn (đơn vừa bị sửa song song thì bỏ qua — chạy lại là bù)")


if __name__ == "__main__":
    main()
