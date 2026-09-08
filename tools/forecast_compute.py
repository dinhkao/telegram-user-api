#!/usr/bin/env python3
"""CLI: tính số liệu dự báo hàng hoá cho 1 ngày → JSON (bước 1 của job 7h sáng).
    .venv/bin/python tools/forecast_compute.py [--ymd YYYY-MM-DD] --out path.json
Đọc app.db chỉ-đọc (utils.paths.SHARED_DB_PATH), gọi forecast_store.engine.compute; kèm
dự báo hôm qua (nếu có) để so thực tế. Nối: forecast_store.{history,engine,queries}.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ymd", default=None)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    from utils.daily_photo_report import today_vn
    from utils.db import get_connection
    import forecast_store
    from forecast_store.engine import compute
    from forecast_store.history import load_lines
    today = dt.date.fromisoformat(a.ymd or today_vn())
    conn = get_connection()
    try:
        forecast_store.ensure_tables(conn)
        prev = forecast_store.get_by_ymd(conn, (today - dt.timedelta(days=1)).isoformat())
        lines = load_lines(conn, today - dt.timedelta(days=420))
    finally:
        conn.close()
    data = compute(lines, today, prev["day_total"] if prev else None)
    txt = json.dumps(data, ensure_ascii=False, indent=1)
    if a.out == "-":
        print(txt)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"ok {a.out} lines={len(lines)} day={data['day']['total']} week={data['week']['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
