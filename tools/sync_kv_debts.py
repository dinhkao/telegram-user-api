"""Đồng bộ CÔNG NỢ toàn bộ khách từ KiotViet về bảng customers (app.db).

Kéo hết khách KV (list_all_customers_kv) → map theo id → vá $.debt +
$.debt_updated_at cho khách local có kh_id khớp (KiotViet là mỏ neo nợ duy
nhất). Báo cáo: số vá / khớp sẵn / kh_id không còn trên KV / local thiếu
kh_id / khách KV chưa có local.

Chạy:  .venv/bin/python tools/sync_kv_debts.py [--dry-run]
Nối: integrations/kiotviet/customers, utils/db (app.db bảng customers).
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv()   # KIOTVIET_CLIENT_ID/SECRET từ .env (core đọc env lúc gọi)

from integrations.kiotviet.customers import list_all_customers_kv
from utils.db import get_connection, transaction


def main() -> None:
    dry = "--dry-run" in sys.argv
    kv = list_all_customers_kv()
    by_id = {int(c["id"]): c for c in kv if c.get("id") is not None}
    print(f"KiotViet: {len(kv)} khách")

    conn = get_connection()
    patched = same = no_khid = stale_khid = 0
    seen_kv_ids: set[int] = set()
    changes: list[str] = []
    try:
        with transaction(conn):
            rows = conn.execute(
                "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"
            ).fetchall()
            now_ms = int(time.time() * 1000)
            for r in rows:
                try:
                    data = json.loads(r["json"])
                except json.JSONDecodeError:
                    continue
                kh_id = data.get("kh_id")
                try:
                    kh_id = int(kh_id) if kh_id is not None else None
                except (TypeError, ValueError):
                    kh_id = None
                if kh_id is None:
                    no_khid += 1
                    continue
                c = by_id.get(kh_id)
                if c is None:
                    stale_khid += 1
                    print(f"  ⚠ kh_id {kh_id} ({data.get('name')}) không còn trên KiotViet")
                    continue
                seen_kv_ids.add(kh_id)
                new_debt = c.get("debt") or 0
                old_debt = data.get("debt")
                try:
                    differs = old_debt is None or abs(float(old_debt) - float(new_debt)) > 0.5
                except (TypeError, ValueError):
                    differs = True
                if not differs:
                    same += 1
                    continue
                patched += 1
                changes.append(f"  {data.get('name')}: {old_debt} → {new_debt}")
                if not dry:
                    data["debt"] = new_debt
                    data["debt_updated_at"] = now_ms
                    conn.execute(
                        "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
                        (json.dumps(data, ensure_ascii=False), now_ms, r["firebase_key"]),
                    )
    finally:
        conn.close()

    only_kv = len(by_id) - len(seen_kv_ids)
    for line in changes:
        print(line)
    print(f"\n{'DRY-RUN — chưa ghi gì. ' if dry else ''}Kết quả:")
    print(f"  vá nợ:              {patched}")
    print(f"  khớp sẵn:           {same}")
    print(f"  local thiếu kh_id:  {no_khid}")
    print(f"  kh_id mất trên KV:  {stale_khid}")
    print(f"  KV chưa có local:   {only_kv}")


if __name__ == "__main__":
    main()
