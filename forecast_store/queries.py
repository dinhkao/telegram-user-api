"""CRUD DỰ BÁO HÀNG HOÁ — `daily_forecasts` + `forecast_views` (app.db). Đăng = upsert
theo ymd (chạy lại trong ngày thì đè, giữ id → link cũ vẫn đúng). created_at UTC ISO.
Dùng bởi server_app.forecast_routes, tools/forecast_publish.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from utils.db import transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r, *, full: bool) -> dict | None:
    if not r:
        return None
    d = dict(r)
    data = {}
    try:
        data = json.loads(d.pop("data_json") or "{}")
    except Exception:  # noqa: BLE001
        d.pop("data_json", None)
    day = data.get("day") or {}
    week = data.get("week") or {}
    out = {
        "id": d["id"], "ymd": d["ymd"], "title": d["title"], "summary": d["summary"],
        "model": d["model"], "created_at": d["created_at"], "updated_at": d["updated_at"],
        "dow_label": data.get("dow_label") or "",
        "lunar_label": (data.get("lunar") or {}).get("label") or "",
        "day_total": day.get("total") or 0, "day_hi": day.get("hi") or 0,
        "week_total": week.get("total") or 0, "week_hi": week.get("hi") or 0,
        "week_from": week.get("from") or "", "week_to": week.get("to") or "",
    }
    if full:
        out["body_md"] = d["body_md"]
        out["data"] = data
    return out


def upsert_forecast(conn, *, ymd: str, title: str, summary: str, body_md: str,
                    data: dict, model: str = "auto", by: str = "") -> tuple[dict, bool]:
    """Đăng/đè bản dự báo của ngày `ymd`. Trả (row, created_new)."""
    ymd = str(ymd).strip()
    if len(ymd) != 10:
        raise ValueError("ymd phải dạng YYYY-MM-DD")
    title = str(title or "").strip() or f"Dự báo hàng hoá {ymd}"
    payload = json.dumps(data or {}, ensure_ascii=False)
    now = _now()
    with transaction(conn):
        cur = conn.execute("SELECT id FROM daily_forecasts WHERE ymd = ?", (ymd,)).fetchone()
        if cur:
            conn.execute(
                "UPDATE daily_forecasts SET title=?, summary=?, body_md=?, data_json=?, model=?, "
                "updated_at=? WHERE id=?",
                (title, summary or "", body_md or "", payload, model or "auto", now, cur["id"]))
            fid, created = cur["id"], False
        else:
            c = conn.execute(
                "INSERT INTO daily_forecasts (ymd, title, summary, body_md, data_json, model, "
                "created_at, updated_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
                (ymd, title, summary or "", body_md or "", payload, model or "auto", now, now, by or ""))
            fid, created = c.lastrowid, True
    return get_forecast(conn, fid), created


def get_forecast(conn, fid, *, full: bool = True) -> dict | None:
    r = conn.execute("SELECT * FROM daily_forecasts WHERE id = ?", (fid,)).fetchone()
    return _row(r, full=full)


def get_by_ymd(conn, ymd: str, *, full: bool = False) -> dict | None:
    r = conn.execute("SELECT * FROM daily_forecasts WHERE ymd = ?", (ymd,)).fetchone()
    return _row(r, full=full)


def list_forecasts(conn, *, limit: int = 30, before_id: int | None = None,
                   username: str | None = None) -> tuple[list[dict], bool]:
    """Mới nhất trước, phân trang theo id. Gắn `viewed` cho `username`."""
    limit = max(1, min(int(limit or 30), 100))
    if before_id:
        rows = conn.execute(
            "SELECT * FROM daily_forecasts WHERE id < ? ORDER BY ymd DESC, id DESC LIMIT ?",
            (int(before_id), limit + 1)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM daily_forecasts ORDER BY ymd DESC, id DESC LIMIT ?", (limit + 1,)).fetchall()
    has_more = len(rows) > limit
    items = [_row(r, full=False) for r in rows[:limit]]
    if username and items:
        ids = [it["id"] for it in items]
        q = ",".join("?" * len(ids))
        seen = {r[0] for r in conn.execute(
            f"SELECT forecast_id FROM forecast_views WHERE username = ? AND forecast_id IN ({q})",
            (username, *ids)).fetchall()}
        for it in items:
            it["viewed"] = it["id"] in seen
    else:
        for it in items:
            it["viewed"] = False
    return items, has_more


def mark_viewed(conn, fid: int, username: str) -> None:
    if not username:
        return
    with transaction(conn):
        conn.execute(
            "INSERT OR IGNORE INTO forecast_views (forecast_id, username, viewed_at) VALUES (?,?,?)",
            (int(fid), username, _now()))


def viewed_by(conn, fid: int, username: str) -> bool:
    if not username:
        return False
    r = conn.execute("SELECT 1 FROM forecast_views WHERE forecast_id = ? AND username = ?",
                     (int(fid), username)).fetchone()
    return bool(r)
