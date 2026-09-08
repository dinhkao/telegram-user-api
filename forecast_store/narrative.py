"""Tự viết TIÊU ĐỀ / TÓM TẮT / NỘI DUNG markdown cho bản dự báo từ số liệu engine — dùng
khi agent Claude không chạy được (mất mạng, hết hạn mức). Giọng BẢN TIN ĐIỀU HÀNH nghiêm
túc: ưu tiên rõ, ít số, so sánh bằng chữ, không xưng hô/khẩu ngữ; bảng số app tự hiện ở dưới.
Thuần, unit-tested. Dùng bởi tools/forecast_publish.py.
"""
from __future__ import annotations


def fmt(n: float | int) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    return f"{int(round(v)):,}".replace(",", ".")


def nice(n: float | int) -> str:
    """Làm tròn cho dễ nhớ: 640 → 'khoảng 650', 3.280 → 'hơn 3.200', 12.380 → 'hơn 12.000'."""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    if v < 100:
        return f"khoảng {int(round(v / 5.0) * 5)}"
    if v < 1000:
        return f"khoảng {int(round(v / 50.0) * 50)}"
    if v < 10000:
        base = int(v // 100 * 100)
        return f"hơn {fmt(base)}" if v - base >= 20 else f"khoảng {fmt(base)}"
    base = int(v // 1000 * 1000)
    return f"hơn {fmt(base)}" if v - base >= 200 else f"khoảng {fmt(base)}"


def _dm(ymd: str) -> str:
    try:
        y, m, d = ymd.split("-")
        return f"{int(d)}/{int(m)}"
    except ValueError:
        return ymd


def _short(name: str) -> str:
    """Tên ngắn kiểu gọi trong xưởng: bỏ phần trong ngoặc, cắt 28 ký tự."""
    s = (name or "").split("(")[0].strip()
    return s[:28].rstrip() if s else ""


def _label(r: dict) -> str:
    s = _short(r.get("name", ""))
    return f"**{r['fam']}** {s}" if s else f"**{r['fam']}**"


def _compare(today: float, yday: float) -> str:
    if yday <= 0:
        return ""
    k = today / yday
    if k >= 1.8:
        return "gấp đôi hôm qua"
    if k >= 1.25:
        return "cao hơn hôm qua rõ rệt"
    if k <= 0.55:
        return "thấp hơn hôm qua nhiều"
    if k <= 0.8:
        return "thấp hơn hôm qua một ít"
    return "tương đương hôm qua"


def title_for(data: dict) -> str:
    return f"Dự báo hàng hoá {data.get('dow_label', '')} {_dm(data.get('ymd', ''))}".strip()


def summary_for(data: dict) -> str:
    day, week, ys = data.get("day") or {}, data.get("week") or {}, data.get("yesterday") or {}
    rows = day.get("rows") or []
    lines = []
    cmp_ = _compare(day.get("total", 0), ys.get("total", 0))
    first = f"Nhu cầu hôm nay khoảng {fmt(day.get('total', 0))} đơn vị"
    lines.append(first + (f", {cmp_}." if cmp_ else "."))
    if rows:
        top = " và ".join(r["fam"] for r in rows[:2])
        lines.append(f"Ưu tiên {top}, hai mã có nhu cầu lớn nhất.")
    lines.append(f"Tuần này còn phải sản xuất {nice(week.get('remain', 0))}.")
    ev = [e for e in (data.get("events") or []) if 0 <= e.get("days", -1) <= 30]
    if ev:
        e = ev[0]
        lines.append(f"{e['name']} còn {e['days']} ngày ({_dm(e['ymd'])}), nhu cầu hàng gói nhỏ tăng dần.")
    return "\n".join(lines)


def auto_narrative(data: dict) -> tuple[str, str, str]:
    """(title, summary, body_md) hoàn toàn từ số liệu, giọng bản tin điều hành."""
    day, week, ys = data.get("day") or {}, data.get("week") or {}, data.get("yesterday") or {}
    rows, wrows = day.get("rows") or [], week.get("rows") or []
    body = ["## Ưu tiên sản xuất hôm nay", ""]
    cmp_ = _compare(day.get("total", 0), ys.get("total", 0))
    body.append(f"Nhu cầu {data.get('dow_label', '')} {nice(day.get('total', 0))} đơn vị"
                + (f", {cmp_}." if cmp_ else "."))
    body.append("")
    for i, r in enumerate(rows[:5]):
        why = ""
        if r.get("factor", 1) >= 1.2:
            why = " — năm ngoái cùng ngày âm lịch tiêu thụ cao, chuẩn bị cao hơn dự báo"
        elif r.get("factor", 1) <= 0.8:
            why = " — năm ngoái cùng ngày âm lịch tiêu thụ thấp, không sản xuất vượt dự báo"
        lead = "ưu tiên 1" if i == 0 else ("ưu tiên 2" if i == 1 else "")
        body.append(f"- {_label(r)}: {nice(r['fc'])} {r.get('unit', '')}" + (f", {lead}" if lead else "") + why + ".")
    body += ["", "## Kế hoạch tuần", ""]
    done = [r for r in wrows if r["fc"] >= 50 and r["remain"] <= 0]
    lack = [r for r in wrows if r["remain"] >= 50][:3]
    body.append(f"Cả tuần còn phải sản xuất {nice(week.get('remain', 0))} (đã bán {nice(week.get('sofar', 0))} từ đầu tuần).")
    if done:
        body.append("Đã đủ cho tuần, không cần sản xuất thêm: " + ", ".join(r["fam"] for r in done[:4]) + ".")
    if lack:
        body.append("Thiếu nhiều nhất: " + ", ".join(f"{r['fam']} còn {nice(r['remain'])}" for r in lack) + ".")
    ev = [e for e in (data.get("events") or []) if e.get("days", -1) >= 0]
    body += ["", "## Yếu tố mùa vụ", ""]
    lunar = data.get("lunar") or {}
    up = [r for r in wrows if r.get("factor", 1) >= 1.2 and r["fc"] >= 50]
    down = [r for r in wrows if r.get("factor", 1) <= 0.8 and r["fc"] >= 50]
    body.append(f"Hôm nay là {lunar.get('label', '')}.")
    if ev:
        body.append(" ".join(f"{e['name']} còn {e['days']} ngày ({_dm(e['ymd'])})." for e in ev[:2]))
    if up:
        body.append("Cùng tuần này năm ngoái tiêu thụ cao: " + ", ".join(r["fam"] for r in up[:4]) + " — cần chuẩn bị sớm.")
    if down:
        body.append("Tiêu thụ thấp hơn thường lệ: " + ", ".join(r["fam"] for r in down[:4]) + " — không sản xuất vượt dự báo.")
    body += ["", "## Lưu ý", ""]
    if ys:
        line = f"Hôm qua ({_dm(ys.get('ymd', ''))}) bán {fmt(ys.get('total', 0))} đơn vị, {ys.get('orders', 0)} đơn"
        if ys.get("forecast") is not None:
            line += f"; dự báo hôm qua là {fmt(ys['forecast'])}"
        body.append(line + ".")
    body.append("_Bản tự động từ số liệu, chưa có nhận định của AI._")
    return title_for(data), summary_for(data), "\n".join(body)
