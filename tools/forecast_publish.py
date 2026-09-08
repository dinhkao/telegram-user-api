#!/usr/bin/env python3
"""CLI: ĐĂNG bản dự báo vào app (bước cuối của job 7h sáng).
    forecast_publish.py --data <compute.json> --draft <draft.json> [--model claude-opus-5]
    forecast_publish.py --data <compute.json> --auto            # tự viết, không có agent
    forecast_publish.py --check YYYY-MM-DD                      # exit 0 nếu ngày đó đã có bản
draft.json = {"title"?, "summary", "body_md"} do agent viết. Gửi POST loopback
/api/forecasts/publish (server bắn realtime + chuông); server không chạy → ghi thẳng DB.
Nối: forecast_store.{narrative,queries}, server_app.forecast_routes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _post(payload: dict) -> dict | None:
    port = os.getenv("PORT", "8090")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/forecasts/publish",
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"server không nhận ({e}) → ghi thẳng DB", file=sys.stderr)
        return None


def _direct(payload: dict) -> dict:
    from utils.db import get_connection
    import forecast_store
    conn = get_connection()
    try:
        forecast_store.ensure_tables(conn)
        row, created = forecast_store.upsert_forecast(
            conn, ymd=payload["ymd"], title=payload["title"], summary=payload["summary"],
            body_md=payload["body_md"], data=payload["data"], model=payload["model"], by=payload["by"])
        return {"ok": True, "id": row["id"], "created": created, "direct": True}
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--draft")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--check", default=None)
    a = ap.parse_args()
    if a.check:
        from utils.db import get_connection
        import forecast_store
        conn = get_connection()
        try:
            forecast_store.ensure_tables(conn)
            row = forecast_store.get_by_ymd(conn, a.check)
        finally:
            conn.close()
        print(json.dumps(row, ensure_ascii=False) if row else "none")
        return 0 if row else 1
    if not a.data:
        ap.error("cần --data")
    with open(a.data, encoding="utf-8") as f:
        data = json.load(f)
    from forecast_store.narrative import auto_narrative, summary_for, title_for
    title, summary, body = auto_narrative(data)
    model = "auto"
    if a.draft and not a.auto:
        with open(a.draft, encoding="utf-8") as f:
            d = json.load(f)
        title = str(d.get("title") or title_for(data)).strip()
        summary = str(d.get("summary") or summary_for(data)).strip()
        body = str(d.get("body_md") or body).strip()
        model = a.model or "claude-opus-5"
        if len(body) < 200:
            print("draft quá ngắn — dùng bản tự động", file=sys.stderr)
            title, summary, body = auto_narrative(data)
            model = "auto"
    payload = {"ymd": data["ymd"], "title": title, "summary": summary, "body_md": body,
               "data": data, "model": model, "by": "cron"}
    res = _post(payload) or _direct(payload)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
