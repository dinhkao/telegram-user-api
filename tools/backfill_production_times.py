"""ĐỒNG BỘ giờ bắt đầu/xong của báo cáo phiếu SX cũ về 1 format "HH:MM" (24h).

Trước 2026-09-26 ô giờ nhập tự do nên blob `production_slips.bang` có đủ kiểu
"7h" · "13g40" · "9h5" · "1415" · "4h15"(=16:15)… Script chỉ sửa 2 key `start`/`end`
trong blob theo `production_store.time_fmt.normalize_time` (cùng luật lúc lưu báo cáo
mới) — không đụng dòng thợ, tiền, `updated_at`. Giá trị không hiểu được thì GIỮ NGUYÊN
và in ra để sửa tay.

MẶC ĐỊNH CHẠY THỬ (chỉ in ra) — thêm --apply mới ghi. Chạy lại lần 2 = không đổi gì.
Nối: production_slips (app.db), production_store.time_fmt.

    .venv/bin/python tools/backfill_production_times.py
    .venv/bin/python tools/backfill_production_times.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production_store.time_fmt import is_time_ok, normalize_time  # noqa: E402
from utils.db import get_connection, transaction  # noqa: E402
from utils.paths import SHARED_DB_PATH  # noqa: E402

_KEYS = ("start", "end")


def plan_changes(rows) -> tuple[list[tuple[int, dict]], list[tuple[int, str, str]]]:
    """rows = [(thread_id, bang_json)] → ([(tid, blob đã sửa)], [(tid, key, giá trị lạ)])."""
    changes, bad = [], []
    for tid, raw in rows:
        try:
            b = json.loads(raw or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(b, dict):
            continue
        new = dict(b)
        for k in _KEYS:
            v = b.get(k)
            if v is None:
                continue
            nv = normalize_time(v) or None
            if nv != v:
                new[k] = nv
            if not is_time_ok(nv):
                bad.append((tid, k, str(v)))
        if new != b:
            changes.append((tid, new))
    return changes, bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ chạy thử)")
    args = ap.parse_args()

    conn = get_connection(SHARED_DB_PATH)
    rows = conn.execute(
        "SELECT thread_id, bang FROM production_slips WHERE bang IS NOT NULL AND bang != ''"
    ).fetchall()
    old = {int(r[0]): json.loads(r[1]) for r in rows if r[1]}
    changes, bad = plan_changes([(int(r[0]), r[1]) for r in rows])
    for tid, b in changes:
        o = old.get(tid) or {}
        print(f"#{tid}: {o.get('start')!r}–{o.get('end')!r}  →  {b.get('start')!r}–{b.get('end')!r}")
    for tid, k, v in bad:
        print(f"⚠ #{tid} {k}={v!r}: không hiểu được, giữ nguyên — sửa tay")
    print(f"\n{len(rows)} phiếu có báo cáo · {len(changes)} phiếu cần sửa · {len(bad)} giá trị lạ")
    if not args.apply:
        print("CHẠY THỬ — thêm --apply để ghi.")
        return
    with transaction(conn):
        for tid, b in changes:
            conn.execute("UPDATE production_slips SET bang = ? WHERE thread_id = ?",
                         (json.dumps(b, ensure_ascii=False), tid))
    print(f"ĐÃ GHI {len(changes)} phiếu.")


if __name__ == "__main__":
    main()
