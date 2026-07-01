"""Di trú dữ liệu app.db (SQLite) -> PostgreSQL, GIỮ NGUYÊN 100% + verify.

Bước 1 của migration (docs/postgres-migration.md): copy blob nguyên bytes, không
reserialize, rồi CHỨNG MINH data y hệt bằng đếm dòng + so byte cột `json` + so full
row. Idempotent: TRUNCATE trước khi nạp. Chạy trên BẢN COPY app.db trước khi prod.

Dùng:
  .venv/bin/python tools/migrate_sqlite_to_pg.py \
      --sqlite /path/to/app.db \
      --pg "postgresql://letrang:letrang@localhost:5432/app" \
      [--verify-only]

Connects: sqlite3 (nguồn), psycopg (đích). Không import gì trong app → chạy độc lập.
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime

import psycopg

# Cột đổi kiểu khi migrate: text/lẫn -> bigint epoch ms (ordering đúng số).
# orders.updated_at & customers.updated_at: int giữ nguyên; chuỗi ISO -> epoch ms.
_COERCE_MS = {("orders", "updated_at"), ("customers", "updated_at")}


def _to_epoch_ms(v):
    """int (đã là ms) giữ nguyên; chuỗi ISO '...Z' -> epoch ms (cùng thời điểm)."""
    if v is None or isinstance(v, int):
        return v
    s = str(v).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))  # aware UTC (Py3.11+)
    return int(round(dt.timestamp() * 1000))


def _coerce_cell(table, col, v):
    return _to_epoch_ms(v) if (table, col) in _COERCE_MS else v

# Cột insertable mỗi bảng (LOẠI generated cols của PG: orders.nop_nhan_done/order_created).
# Thứ tự khớp cả 2 engine. id (IDENTITY) đưa vào để giữ nguyên khóa.
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
# Bảng có IDENTITY cần đồng bộ sequence sau khi nạp id tường minh.
IDENTITY_TABLES = {"order_chat_messages": "id", "audit_events": "id"}
PK = {  # để sắp xếp khi verify
    "kv_store": "path", "orders": "firebase_key", "order_key_by_thread": "thread_id",
    "order_key_by_message": "message_id", "order_discussion_mirror": "channel_message_id",
    "kv_revisions": "path", "customers": "firebase_key", "tasks": "firebase_key",
    "products": "code", "order_chat_messages": "id", "audit_events": "id",
    "production_slips": "thread_id", "bang_gia_slips": "thread_id", "notes": "thread_id",
}


def sqlite_rows(scon, table, cols):
    q = f"SELECT {', '.join(cols)} FROM {table}"
    return scon.execute(q).fetchall()


def load(scon, pcon):
    for table, cols in TABLES.items():
        rows = sqlite_rows(scon, table, cols)
        with pcon.cursor() as cur:
            cur.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")
            if rows:
                collist = ", ".join(cols)
                with cur.copy(f"COPY {table} ({collist}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(tuple(_coerce_cell(table, cols[i], v) for i, v in enumerate(r)))
            if table in IDENTITY_TABLES:
                idcol = IDENTITY_TABLES[table]
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                    f"COALESCE((SELECT MAX({idcol}) FROM {table}), 1))",
                    (table, idcol),
                )
        pcon.commit()
        print(f"  nạp {table:24} {len(rows):7} dòng")


def _norm(v):
    # SQLite trả bytes cho một số cột? json là text. Chuẩn hóa để so sánh cross-engine.
    if isinstance(v, memoryview):
        return bytes(v)
    return v


def verify(scon, pcon):
    ok = True
    print("\n=== VERIFY ===")
    for table, cols in TABLES.items():
        pk = PK[table]
        scount = scon.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        with pcon.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            pcount = cur.fetchone()[0]
        cmark = "OK" if scount == pcount else "MISMATCH"
        if scount != pcount:
            ok = False
        print(f"  {table:24} count sqlite={scount:7} pg={pcount:7} [{cmark}]")

        # So byte cột json (nếu có) — bằng chứng blob y hệt.
        if "json" in cols:
            srows = {r[0]: r[1] for r in scon.execute(f"SELECT {pk}, json FROM {table}").fetchall()}
            with pcon.cursor() as cur:
                cur.execute(f"SELECT {pk}, json FROM {table}")
                prows = {r[0]: r[1] for r in cur.fetchall()}
            diff = 0
            for k, sv in srows.items():
                if prows.get(k) != sv:
                    diff += 1
                    if diff <= 3:
                        print(f"      JSON DIFF pk={k!r}")
            jmark = "OK" if diff == 0 else f"{diff} DIFF"
            if diff:
                ok = False
            print(f"      json byte-identity: [{jmark}]")

        # Checksum full-row str-normalized (SQLite int vs PG text chỉ khác repr, không
        # khác giá trị — chuẩn hóa "" cho NULL + str() mọi cột trước khi băm).
        def digest(rows, coerce=False):
            h = hashlib.md5()
            if coerce:
                rows = [tuple(_coerce_cell(table, cols[i], v) for i, v in enumerate(r)) for r in rows]
            norm = [tuple("" if v is None else str(_norm(v)) for v in r) for r in rows]
            for r in sorted(norm):
                h.update(repr(r).encode("utf-8", "replace"))
            return h.hexdigest()
        srowsf = scon.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        with pcon.cursor() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM {table}")
            prowsf = cur.fetchall()
        # coerce phía SQLite giống migrate -> nếu KHỚP nghĩa là CHỈ updated_at đổi
        # đúng như chủ đích, không cột nào khác drift.
        sd, pd = digest(srowsf, coerce=True), digest(prowsf)
        if sd != pd:
            ok = False
        print(f"      full-row md5 (coerced): {'OK' if sd == pd else 'DIFFER'}")
    print("\nRESULT:", "✅ COUNT + JSON BYTE-IDENTITY KHỚP" if ok else "❌ CÓ LỆCH — DỪNG")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--pg", required=True)
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    scon = sqlite3.connect(a.sqlite)
    scon.text_factory = str
    pcon = psycopg.connect(a.pg)
    try:
        if not a.verify_only:
            print("=== LOAD ===")
            load(scon, pcon)
        ok = verify(scon, pcon)
    finally:
        scon.close()
        pcon.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
