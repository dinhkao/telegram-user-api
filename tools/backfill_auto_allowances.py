"""CHẠY BÙ phụ cấp tự động cho các phiếu SX ĐÃ LƯU (rule chỉ áp lúc lưu báo cáo).

Sửa bảng RULE ở production_store/allowance_auto.py xong thì phiếu cũ vẫn giữ số phụ cấp
tính theo rule CŨ — script này duyệt lại từng phiếu trong khoảng ngày và áp rule HIỆN TẠI.
Tôn trọng số văn phòng nhập tay y như lúc lưu báo cáo (chỉ đụng dòng updated_by='auto').

MẶC ĐỊNH CHẠY THỬ (chỉ in ra, không ghi) — thêm --apply mới ghi vào DB.
Nối: production_store.allowance_auto (plan/apply), production_slips, production_report_rows.

    .venv/bin/python tools/backfill_auto_allowances.py --from 2026-07-01 --to 2026-07-31
    .venv/bin/python tools/backfill_auto_allowances.py --from 2026-07-01 --to 2026-07-31 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production_store.allowance_auto import apply_auto_allowances, plan_auto_allowances  # noqa: E402
from utils.db import get_connection  # noqa: E402
from utils.paths import SHARED_DB_PATH  # noqa: E402


def _slips_in_range(conn, dfrom: str, dto: str) -> list[tuple[int, str]]:
    """[(thread_id, ngày báo cáo sớm nhất)] các phiếu CÓ dòng báo cáo trong khoảng."""
    rows = conn.execute(
        "SELECT thread_id, MIN(report_ymd) AS ymd FROM production_report_rows "
        "WHERE report_ymd IS NOT NULL AND report_ymd >= ? AND report_ymd <= ? "
        "GROUP BY thread_id ORDER BY ymd ASC, thread_id ASC",
        (dfrom, dto),
    ).fetchall()
    return [(int(r[0]), str(r[1] or "")) for r in rows]


def _bang(conn, thread_id: int) -> dict:
    r = conn.execute(
        "SELECT bang FROM production_slips WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if not r or not r[0]:
        return {}
    try:
        b = json.loads(r[0])
    except (TypeError, ValueError):
        return {}
    return b if isinstance(b, dict) else {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Chạy bù phụ cấp tự động cho phiếu SX đã lưu")
    ap.add_argument("--from", dest="dfrom", required=True, help="ngày bắt đầu YYYY-MM-DD")
    ap.add_argument("--to", dest="dto", required=True, help="ngày kết thúc YYYY-MM-DD")
    ap.add_argument("--db", default=SHARED_DB_PATH, help=f"đường dẫn app.db (mặc định {SHARED_DB_PATH})")
    ap.add_argument("--apply", action="store_true", help="GHI THẬT (mặc định chỉ chạy thử)")
    args = ap.parse_args()

    conn = get_connection(args.db)
    slips = _slips_in_range(conn, args.dfrom, args.dto)
    print(f"{'GHI THẬT' if args.apply else 'CHẠY THỬ'} · {len(slips)} phiếu "
          f"{args.dfrom} → {args.dto} · {args.db}\n")

    per_worker: dict[str, list[float]] = {}
    n_changed = 0
    for tid, ymd in slips:
        bang = _bang(conn, tid)
        if not bang:
            continue
        try:
            changes = plan_auto_allowances(conn, tid, bang)
        except Exception as e:  # noqa: BLE001 — 1 phiếu hỏng không được chặn cả lượt
            print(f"  ⚠ phiếu {tid} ({ymd}): {e}")
            continue
        if not changes:
            continue
        n_changed += 1
        for ch in changes:
            delta = ch["new"] - ch["old"]
            per_worker.setdefault(ch["name"], []).append(delta)
            print(f"  {ymd} phiếu {tid:>7} · {ch['name']:<12} "
                  f"{ch['old']:>12,.0f} → {ch['new']:>12,.0f}  ({delta:+,.0f})")
        if args.apply:
            apply_auto_allowances(conn, tid, bang)

    print(f"\nTổng: {n_changed} phiếu đổi")
    for name in sorted(per_worker, key=lambda n: -sum(per_worker[n])):
        d = per_worker[name]
        print(f"  {name:<12} {len(d):>4} khoản  {sum(d):>+14,.0f} đ")
    total = sum(sum(d) for d in per_worker.values())
    print(f"  {'TỔNG':<12} {sum(len(d) for d in per_worker.values()):>4} khoản  {total:>+14,.0f} đ")
    if not args.apply:
        print("\n(chạy thử — chưa ghi gì. Thêm --apply để ghi thật)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
