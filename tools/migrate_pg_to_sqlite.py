"""Di trú NGƯỢC PostgreSQL -> SQLite (quay lại SQLite, giữ mọi write sau cutover).

Đối xứng với migrate_sqlite_to_pg.py. Dùng file SQLite đích LÀM SẴN schema (copy từ
app.db gốc): xóa data cũ, nạp lại từ PG. json blob giữ nguyên bytes; updated_at (PG
bigint) ghi vào cột INTEGER của SQLite. Cột generated (order_created, nop_nhan_done)
là VIRTUAL trong SQLite — không insert, tự tính.

Dùng:
  cp ~/letrang-db/app.db /tmp/app_rebuilt.db      # lấy schema gốc
  .venv/bin/python tools/migrate_pg_to_sqlite.py \
      --sqlite /tmp/app_rebuilt.db \
      --pg "postgresql://duydinh0225@/app?host=/tmp"
  # verify OK -> mv /tmp/app_rebuilt.db ~/letrang-db/app.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

import psycopg

# Cùng danh sách cột insertable như chiều xuôi (loại cột generated).
TABLES: dict[str, list[str]] = {
    "kv_store": ["path", "value", "updated_at"],
    "orders": ["firebase_key", "thread_id", "channel_id", "message_id", "json", "updated_at", "deleted_at"],
    "order_key_by_thread": ["thread_id", "firebase_key"],
    "order_key_by_message": ["message_id", "firebase_key"],
    "order_discussion_mirror": ["channel_message_id", "json", "updated_at"],
    "kv_revisions": ["path", "rev"],
    "customers": ["firebase_key", "json", "updated_at", "deleted_at"],
    "tasks": ["firebase_key", "json", "updated_at", "deleted_at"],
    "products": ["code", "name", "cost_price", "note", "created_at", "updated_at"],
    "order_chat_messages": ["id", "thread_id", "message_id", "sender_id", "sender_name", "text",
                             "media_type", "created_at", "event_type", "raw_json", "edited_at", "deleted_at"],
    "audit_events": ["id", "ts", "request_id", "actor_type", "actor_id", "action", "direction", "source",
                      "chat_id", "thread_id", "message_id", "payload_json", "result_json", "error", "duration_ms"],
    "production_slips": ["thread_id", "channel_id", "message_id", "date", "date_code", "sp_name", "sp_mam",
                          "sp_luong", "sx_target", "total", "numbers", "bang", "updated_at"],
    "bang_gia_slips": ["thread_id", "name", "price_list", "updated_at"],
    "notes": ["thread_id", "text", "tags", "check_flag", "del_flag", "channel_id", "message_id", "updated_at"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--pg", required=True)
    a = ap.parse_args()

    sq = sqlite3.connect(a.sqlite)
    sq.text_factory = str
    pg = psycopg.connect(a.pg)
    ok = True
    try:
        for table, cols in TABLES.items():
            pg_rows = pg.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            sq.execute(f"DELETE FROM {table}")
            if pg_rows:
                ph = ", ".join(["?"] * len(cols))
                sq.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})",
                    [tuple(r) for r in pg_rows],
                )
            sq.commit()
            # verify count
            sc = sq.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            mark = "OK" if sc == len(pg_rows) else "MISMATCH"
            if sc != len(pg_rows):
                ok = False
            print(f"  {table:24} pg={len(pg_rows):7} -> sqlite={sc:7} [{mark}]")
        # verify json byte-identity trên orders
        pj = {r[0]: r[1] for r in pg.execute("SELECT firebase_key, json FROM orders").fetchall()}
        sj = {r[0]: r[1] for r in sq.execute("SELECT firebase_key, json FROM orders").fetchall()}
        diff = sum(1 for k in pj if pj[k] != sj.get(k))
        print(f"\n  orders json byte-identity: {'OK' if diff == 0 else f'{diff} DIFF'}")
        if diff:
            ok = False
    finally:
        sq.close()
        pg.close()
    print("\nRESULT:", "✅ PG -> SQLite KHỚP" if ok else "❌ LỆCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
