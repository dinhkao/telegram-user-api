"""Tự viết TIÊU ĐỀ / TÓM TẮT / NỘI DUNG markdown cho bản dự báo từ số liệu engine — dùng
khi agent Claude không chạy được (mất mạng, hết hạn mức) hoặc làm bản nháp cho agent
sửa. Thuần, unit-tested. Dùng bởi tools/forecast_publish.py.
"""
from __future__ import annotations


def fmt(n: float | int) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    s = f"{int(round(v)):,}".replace(",", ".")
    return s


def _dm(ymd: str) -> str:
    try:
        y, m, d = ymd.split("-")
        return f"{int(d)}/{int(m)}"
    except ValueError:
        return ymd


def title_for(data: dict) -> str:
    return f"Dự báo hàng hoá {data.get('dow_label', '')} {_dm(data.get('ymd', ''))}".strip()


def summary_for(data: dict) -> str:
    day, week = data.get("day") or {}, data.get("week") or {}
    top = ", ".join(f"{r['fam']} {fmt(r['fc'])}" for r in (day.get("rows") or [])[:3])
    lines = [
        f"Hôm nay cần khoảng {fmt(day.get('total', 0))} đơn vị (chuẩn bị tới {fmt(day.get('hi', 0))}).",
        f"Tuần này ~{fmt(week.get('total', 0))}, đã bán {fmt(week.get('sofar', 0))}, còn {fmt(week.get('remain', 0))}.",
    ]
    if top:
        lines.append("Nhiều nhất: " + top + ".")
    ev = [e for e in (data.get("events") or []) if 0 <= e.get("days", -1) <= 30]
    if ev:
        lines.append("; ".join(f"{e['name']} còn {e['days']} ngày ({_dm(e['ymd'])})" for e in ev) + ".")
    return "\n".join(lines)


def auto_narrative(data: dict) -> tuple[str, str, str]:
    """(title, summary, body_md) hoàn toàn từ số liệu."""
    day, week = data.get("day") or {}, data.get("week") or {}
    lunar = data.get("lunar") or {}
    body = [f"## Hôm nay — {data.get('dow_label', '')} {_dm(data.get('ymd', ''))} ({lunar.get('label', '')})", ""]
    body.append(f"Dự báo **{fmt(day.get('total', 0))}** đơn vị, chuẩn bị tới **{fmt(day.get('hi', 0))}**. "
                f"Thứ này chiếm {round((day.get('dow_share') or 0) * 100)}% lượng bán trong tuần.")
    body.append("")
    body.append("| Nhóm | Dự báo | Chuẩn bị |")
    body.append("|---|---:|---:|")
    for r in (day.get("rows") or [])[:10]:
        body.append(f"| {r['fam']} — {r['name']} | {fmt(r['fc'])} {r['unit']} | {fmt(r['hi'])} |")
    body += ["", f"## Tuần này — {_dm(week.get('from', ''))} → {_dm(week.get('to', ''))}", ""]
    body.append(f"Dự báo cả tuần **{fmt(week.get('total', 0))}** (nhịp 4 tuần gần nhất {fmt(week.get('w4avg_total', 0))}/tuần). "
                f"Đã bán {fmt(week.get('sofar', 0))}, còn cần **{fmt(week.get('remain', 0))}**.")
    body.append("")
    body.append("| Nhóm | Dự báo tuần | Đã bán | Còn cần |")
    body.append("|---|---:|---:|---:|")
    for r in (week.get("rows") or [])[:10]:
        body.append(f"| {r['fam']} — {r['name']} | {fmt(r['fc'])} {r['unit']} | {fmt(r['sofar'])} | {fmt(r['remain'])} |")
    up = [r for r in (week.get("rows") or []) if r.get("factor", 1) >= 1.2 and r["fc"] >= 50]
    down = [r for r in (week.get("rows") or []) if r.get("factor", 1) <= 0.8 and r["fc"] >= 50]
    if up or down:
        body += ["", "## Theo âm lịch năm ngoái", ""]
        if up:
            body.append("- Tuần này năm ngoái **tăng**: " + ", ".join(f"{r['fam']} (×{r['factor']})" for r in up))
        if down:
            body.append("- Tuần này năm ngoái **giảm**: " + ", ".join(f"{r['fam']} (×{r['factor']})" for r in down))
    ys = data.get("yesterday") or {}
    if ys:
        line = f"Hôm qua ({_dm(ys.get('ymd', ''))}) bán {fmt(ys.get('total', 0))} đơn vị, {ys.get('orders', 0)} đơn"
        if ys.get("forecast") is not None:
            line += f" — dự báo hôm qua là {fmt(ys['forecast'])}"
        body += ["", "## Hôm qua", "", line + "."]
    ev = [e for e in (data.get("events") or []) if e.get("days", -1) >= 0]
    if ev:
        body += ["", "## Sắp tới", ""]
        for e in ev:
            body.append(f"- {e['name']}: {_dm(e['ymd'])} (còn {e['days']} ngày)")
    body += ["", "_Bản tự động từ số liệu, chưa có nhận định của AI._"]
    return title_for(data), summary_for(data), "\n".join(body)
