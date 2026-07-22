"""Dựng báo cáo chấm công hôm nay thành HTML để renderer Playwright chụp PNG."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

_VN = timezone(timedelta(hours=7))


def today_vn() -> str:
    return datetime.now(_VN).strftime("%Y-%m-%d")


def _mins(value: str) -> int:
    try:
        h, m = value[:5].split(":")
        return int(h) * 60 + int(m)
    except (ValueError, IndexError):
        return -1


def _needs_check(times: list[str]) -> bool:
    if len(times) % 2:
        return True
    values = [_mins(t) for t in times]
    for i in range(0, len(values), 2):
        if values[i] < 0 or values[i + 1] < 0:
            return True
        duration = values[i + 1] - values[i]
        if duration < 30 and 7 * 60 <= values[i] and values[i + 1] <= 17 * 60:
            return True
        if values[i] <= 11 * 60 and values[i + 1] >= 13 * 60:
            return True
    return False


def _people(rows: list[dict], workers: list[dict], day: str) -> list[dict]:
    people: dict[str, dict] = {}
    for worker in workers:
        people[f"w:{worker['id']}"] = {
            "name": worker["name"], "codes": [], "times": [], "mapped": True,
            "sort": worker.get("sort_order") or 0,
        }

    for row in rows:
        if row.get("day") != day:
            continue
        worker_id = row.get("worker_id")
        key = f"w:{worker_id}" if worker_id is not None else f"c:{row.get('employee_code', '')}"
        if key not in people:
            people[key] = {
                "name": row.get("worker_name") or f"Mã {row.get('employee_code', '')}",
                "codes": [], "times": [], "mapped": False, "sort": 100000,
            }
        person = people[key]
        code = str(row.get("employee_code") or "").strip()
        if code and code not in person["codes"]:
            person["codes"].append(code)
        person["times"].extend(str(t) for t in (row.get("times") or []) if t)
        if row.get("worker_name"):
            person["name"] = row["worker_name"]

    for person in people.values():
        person["times"].sort()
        person["code"] = " / ".join(person["codes"]) if person["codes"] else "—"
    return sorted(people.values(), key=lambda p: (
        not p["mapped"], p["sort"], str(p["name"]).casefold()))


def build_today_html(day: str, rows: list[dict], workers: list[dict]) -> str:
    people = _people(rows, workers, day)
    present = sum(bool(p["times"]) for p in people)
    issues = sum(bool(p["times"]) and _needs_check(p["times"]) for p in people)
    date_label = f"{day[8:10]}/{day[5:7]}/{day[:4]}"

    body_rows = []
    for index, person in enumerate(people, 1):
        times = "  →  ".join(person["times"]) if person["times"] else "Chưa có record"
        status = "CHƯA CHẤM" if not person["times"] else "CẦN KIỂM TRA" if _needs_check(person["times"]) else "ĐỦ CẶP"
        status_class = "missing" if status == "CHƯA CHẤM" else "warning" if status == "CẦN KIỂM TRA" else "ok"
        body_rows.append(f"""
          <tr>
            <td class="index">{index:02d}</td>
            <td class="person"><strong>{escape(str(person['name']))}</strong></td>
            <td class="code">{escape(person['code'])}</td>
            <td class="times {'empty' if not person['times'] else ''}">{escape(times)}</td>
            <td><span class="status {status_class}">{status}</span></td>
          </tr>""")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; width: 1080px; background: #f5f2ea; color: #17231f; }}
body {{ font-family: Arial, sans-serif; padding: 28px; }}
.sheet {{ width: 1024px; background: #fff; }}
.hero {{ padding: 32px 38px 28px; color: #fffaf1; background: #17322c; }}
.eyebrow {{ color: #b9e5c4; font: 700 18px ui-monospace, monospace; letter-spacing: .3px; }}
h1 {{ margin: 18px 0 16px; font: 700 42px Georgia, serif; }}
.summary {{ color: #dce9df; font: 600 18px ui-monospace, monospace; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
col.index {{ width: 7%; }} col.person {{ width: 36%; }} col.code {{ width: 12%; }}
col.times {{ width: 31%; }} col.state {{ width: 14%; }}
thead {{ color: #486256; background: #e5eee5; font: 800 15px ui-monospace, monospace; text-align: left; }}
th, td {{ padding: 18px 14px; vertical-align: middle; border-bottom: 1px solid #dcded7; }}
th:first-child, td:first-child {{ padding-left: 38px; }}
th:last-child, td:last-child {{ padding-right: 28px; }}
tbody tr:nth-child(even) {{ background: #fbfaf6; }}
.index {{ color: #6d8175; font: 700 16px ui-monospace, monospace; }}
.person strong {{ font-size: 20px; }}
.code {{ color: #4e665b; font: 700 17px ui-monospace, monospace; word-break: break-word; }}
.times {{ color: #22372d; font: 700 17px ui-monospace, monospace; line-height: 1.5; overflow-wrap: anywhere; }}
.times.empty {{ color: #a27a3b; font: 600 16px Arial, sans-serif; }}
.status {{ display: inline-block; padding: 8px 10px; border-radius: 18px; color: white; font: 800 11px Arial, sans-serif; white-space: nowrap; }}
.status.ok {{ background: #2f7a47; }} .status.warning {{ background: #c45832; }} .status.missing {{ background: #a86f17; }}
footer {{ padding: 20px 38px; color: #69786f; background: #e9e6dc; font-size: 14px; }}
</style></head><body><main class="sheet">
  <header class="hero">
    <div class="eyebrow">BẢNG CHẤM CÔNG · BÁO CÁO TRONG NGÀY</div>
    <h1>Chấm công hôm nay</h1>
    <div class="summary">{date_label} &nbsp;·&nbsp; {len(people)} nhân viên &nbsp;·&nbsp; {present} có chấm &nbsp;·&nbsp; {issues} cần kiểm tra</div>
  </header>
  <table><colgroup><col class="index"><col class="person"><col class="code"><col class="times"><col class="state"></colgroup>
    <thead><tr><th>#</th><th>NHÂN VIÊN</th><th>MÃ</th><th>MỌI GIỜ CHẤM</th><th>TRẠNG THÁI</th></tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
  <footer>Tạo từ dashboard Chấm công · Giờ hiển thị theo dữ liệu máy và giờ thêm tay đã lưu</footer>
</main></body></html>"""
