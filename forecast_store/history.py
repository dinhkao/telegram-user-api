"""Đọc LỊCH SỬ BÁN từ blob đơn (`orders.json` → invoice/invoice_items) thành dòng phẳng
cho engine dự báo: 1 dòng = 1 mặt hàng của 1 đơn, ngày = giờ tạo đổi sang giờ VN, mã
resolve về bản hiện hành qua `products` (sp_id), `fam` = mã gốc trước dấu '-'
(gộp biến thể tem -TS/-TD/-KOTEM). Đọc chỉ-đọc, không sửa DB. Dùng bởi engine/CLI.
"""
from __future__ import annotations

import datetime as dt
import json

_VN = dt.timezone(dt.timedelta(hours=7))


def _fam(code: str) -> str:
    return (code or "").split("-")[0].upper()


def load_lines(conn, since: dt.date) -> list[dict]:
    """Dòng hàng của mọi đơn CHƯA XOÁ tạo từ `since` (ngày VN). Mỗi dòng:
    {date, tid, fam, code, name, unit, sl}. Bỏ dòng chiết khấu / sl ≤ 0."""
    prods = {r[0]: (str(r[1] or "").upper(), r[2] or "", r[3] or "")
             for r in conn.execute("SELECT id, code, name, unit FROM products")}
    since_utc = (dt.datetime.combine(since, dt.time()) - dt.timedelta(hours=7)).isoformat()
    rows = conn.execute(
        "SELECT thread_id, json_extract(json,'$.created'), "
        "coalesce(json_extract(json,'$.invoice'), json_extract(json,'$.invoice_items')), "
        "json_extract(json,'$.del') FROM orders "
        "WHERE deleted_at IS NULL AND json_extract(json,'$.created') >= ?", (since_utc,)).fetchall()
    out: list[dict] = []
    for tid, created, inv, dele in rows:
        if dele or not inv or not created:
            continue
        try:
            items = json.loads(inv)
            t = dt.datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(_VN)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(items, list):
            continue
        d = t.date()
        if d < since:
            continue
        for it in items:
            if not isinstance(it, dict) or it.get("kind") == "chiet_khau":
                continue
            code = str(it.get("sp") or "").upper()
            name, unit = str(it.get("name") or ""), ""
            p = prods.get(it.get("sp_id"))
            if p:
                code, name, unit = p
            try:
                sl = float(it.get("sl") or 0)
            except (TypeError, ValueError):
                sl = 0.0
            if sl <= 0 or not code:
                continue
            out.append({"date": d, "tid": tid, "fam": _fam(code), "code": code,
                        "name": name, "unit": unit, "sl": sl})
    return out
