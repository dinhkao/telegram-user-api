"""HTML export builder (faithful port of buildHtml), grouped by STT."""
from __future__ import annotations
from .escape import escape_html, is_finite_number


def _group_body_rows(body_rows, stt_idx, product_idx, total_sp_idx):
    groups, group_map = [], {}
    for row in body_rows:
        stt_raw = ""
        if 0 <= stt_idx < len(row):
            stt_raw = ("" if row[stt_idx] is None else str(row[stt_idx])).strip()
        key = stt_raw or "—"
        group = group_map.get(key)
        if group is None:
            group = {"stt": stt_raw, "rows": [], "products": [], "seen": set(), "totalSp": 0.0}
            group_map[key] = group
            groups.append(group)
        if 0 <= product_idx < len(row):
            p = ("" if row[product_idx] is None else str(row[product_idx])).strip()
            if p and p not in group["seen"]:
                group["seen"].add(p)
                group["products"].append(p)
        if 0 <= total_sp_idx < len(row):
            raw = ("0" if row[total_sp_idx] is None else str(row[total_sp_idx])).replace(",", ".")
            try:
                group["totalSp"] += float(raw)
            except ValueError:
                pass
        group["rows"].append(row)

    def sort_key(g):
        try:
            num = float(g["stt"])
            return (0, num) if is_finite_number(num) else (1, g["stt"] or "")
        except (ValueError, TypeError):
            return (1, g["stt"] or "")

    groups.sort(key=sort_key)
    return groups


def _render_group(g, head_cells):
    prod_list = ", ".join(escape_html(p) for p in g["products"]) if g["products"] else "—"
    total = g["totalSp"]
    total_display = total if is_finite_number(total) else ""
    if isinstance(total_display, float) and total_display.is_integer():
        total_display = int(total_display)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{escape_html(c or '')}</td>" for c in r) + "</tr>" for r in g["rows"]
    )
    return f"""
    <div class="group">
      <div class="group-meta">
        <span><strong>STT:</strong> {escape_html(g['stt'] or '—')}</span>
        <span><strong>Sản phẩm:</strong> {prod_list}</span>
        <span><strong>Tổng số SP:</strong> {escape_html(str(total_display))}</span>
      </div>
      <table>
        <thead><tr>{head_cells}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


def build_html(sheet_name: str, rows: list) -> str:
    safe_name = escape_html(sheet_name)
    header = rows[0] if rows else []
    body_rows = rows[1:] if rows else []

    def find_idx(name):
        for i, h in enumerate(header):
            if ("" if h is None else str(h)).strip() == name:
                return i
        return -1

    head_cells = "".join(f"<th>{escape_html(c or '')}</th>" for c in header)
    groups = _group_body_rows(body_rows, find_idx("STT"), find_idx("Sản phẩm"), find_idx("Tổng số SP"))
    sections = [_render_group(g, head_cells) for g in groups]

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>{safe_name}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 12px; }}
    h1 {{ font-size: 16px; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 6px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .group {{ margin-bottom: 16px; }}
    .group-meta {{ display: flex; gap: 12px; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>{safe_name}</h1>
  {chr(10).join(sections)}
</body>
</html>"""
