"""Logic THUẦN kho đậu (KHÔNG IO, unit-tested: tests/test_bean_store.py).

Chuẩn hoá số lượng, luật dấu của từng loại phiếu (nhập +, xuất −, điều chỉnh =
đếm − tồn), và ghép bảng tồn (đậu × vị trí) cho dashboard. Dùng bởi
bean_store.slips/stock và server_app.bean_routes.
"""
from __future__ import annotations

from utils.daily_photo_report import today_vn

__all__ = ["KINDS", "KIND_LABELS", "today_vn", "parse_qty", "fmt_qty", "round_qty",
           "delta_for", "build_stock_table", "STOCKTAKE_STATUSES", "STOCKTAKE_STATUS_LABELS",
           "count_to_base", "stocktake_summary"]

# Trạng thái phiếu KIỂM KHO: draft = đang đếm · done = đã chốt (đã sinh phiếu điều
# chỉnh) · voided = huỷ (không đụng tồn).
STOCKTAKE_STATUSES = ("draft", "done", "voided")
STOCKTAKE_STATUS_LABELS = {"draft": "Đang kiểm", "done": "Đã chốt", "voided": "Đã huỷ"}

# nhap = nhập kho · xuat = xuất kho · dieu_chinh = phiếu điều chỉnh (đếm thực tế)
# chuyen = chuyển giữa 2 kho: bút toán kép −q kho nguồn / +q kho đích, tồn tổng bảo toàn
KINDS = ("nhap", "xuat", "dieu_chinh", "chuyen")
KIND_LABELS = {"nhap": "Nhập kho", "xuat": "Xuất kho", "dieu_chinh": "Điều chỉnh",
               "chuyen": "Chuyển kho"}


def round_qty(v: float) -> float:
    """Làm tròn 3 chữ số thập phân — đậu cân theo kg, tránh rác dấu phẩy động."""
    return round(float(v or 0), 3)


def parse_qty(v) -> float | None:
    """Số lượng người dùng nhập → float. Nhận '12,5' kiểu Việt. None nếu không đọc được."""
    if v is None:
        return None
    s = str(v).strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return round_qty(float(s))
    except ValueError:
        return None


def fmt_qty(v: float) -> str:
    """Số lượng cho người đọc: bỏ .0 thừa, dấu thập phân là ',' kiểu Việt (120,5)."""
    return f"{round_qty(v):g}".replace(".", ",")


def delta_for(kind: str, quantity: float, before: float) -> float:
    """Số CỘNG vào tồn của 1 dòng phiếu.

    nhap  → +quantity · xuat → −quantity ·
    dieu_chinh → quantity là số ĐẾM THỰC TẾ nên delta = đếm − tồn hiện tại ·
    chuyen → −quantity (PHÍA KHO NGUỒN; dòng +q ở kho đích do slips ghi thêm).
    """
    q = round_qty(quantity)
    if kind == "nhap":
        return q
    if kind in ("xuat", "chuyen"):
        return -q
    if kind == "dieu_chinh":
        return round_qty(q - round_qty(before))
    raise ValueError(f"Loại phiếu lạ: {kind}")


def build_stock_table(beans: list[dict], places: list[dict], cells: list[dict]) -> dict:
    """Ghép tồn thành bảng đọc được nhiều KIỂU (theo đậu / theo vị trí / ô chi tiết).

    cells = [{bean_id, place_id, qty}] (đã gộp sẵn từ SQL). Trả:
      by_bean  = [{id, name, unit, note, total, places: [{place_id, qty}]}]
      by_place = [{id, name, note, total, beans: [{bean_id, qty}]}]
      total    = tổng toàn kho (chỉ có nghĩa khi mọi loại đậu cùng đơn vị)
    Dòng tồn 0 vẫn giữ ở by_bean/by_place (danh mục đầy đủ), ô 0 thì bỏ.
    """
    qty: dict[tuple[int, int], float] = {}
    for c in cells:
        key = (int(c["bean_id"]), int(c["place_id"]))
        qty[key] = round_qty(qty.get(key, 0.0) + float(c.get("qty") or 0))

    by_bean = []
    for b in beans:
        bid = int(b["id"])
        rows = [{"place_id": int(p["id"]), "qty": qty.get((bid, int(p["id"])), 0.0)}
                for p in places]
        rows = [r for r in rows if r["qty"]]
        by_bean.append({
            "id": bid, "name": b.get("name") or "", "unit": b.get("unit") or "kg",
            "note": b.get("note") or "",
            "total": round_qty(sum(r["qty"] for r in rows)),
            "places": rows,
        })

    by_place = []
    for p in places:
        pid = int(p["id"])
        rows = [{"bean_id": int(b["id"]), "qty": qty.get((int(b["id"]), pid), 0.0)}
                for b in beans]
        rows = [r for r in rows if r["qty"]]
        by_place.append({
            "id": pid, "name": p.get("name") or "", "note": p.get("note") or "",
            "total": round_qty(sum(r["qty"] for r in rows)),
            "beans": rows,
        })

    return {
        "by_bean": by_bean,
        "by_place": by_place,
        "total": round_qty(sum(r["total"] for r in by_bean)),
    }


def count_to_base(bulk, loose, factor) -> float | None:
    """Số đếm gõ kép [N đơn vị quy đổi] + [M đơn vị gốc] → số theo ĐƠN VỊ GỐC.

    Cả 2 ô trống → None (= CHƯA ĐẾM, khác hẳn đếm ra 0). Một ô trống coi là 0.
    factor = 1 đơn vị quy đổi bằng bao nhiêu gốc (không có đơn vị phụ → 1).
    """
    if bulk is None and loose is None:
        return None
    return round_qty(float(bulk or 0) * float(factor or 1) + float(loose or 0))


def stocktake_summary(items: list[dict]) -> dict:
    """Tóm tắt phiếu kiểm: bao nhiêu dòng đã đếm, khớp / thừa / thiếu và tổng chênh
    lệch (theo đơn vị gốc — chỉ có nghĩa khi các loại đậu cùng đơn vị).

    Mỗi item cần `expected_qty` + `counted_qty` (None = chưa đếm). `diff` từng dòng
    = đếm − sổ; dòng chưa đếm không tính vào thừa/thiếu.
    """
    total = len(items)
    counted = over = short = match = 0
    sum_over = sum_short = 0.0
    for it in items:
        c = it.get("counted_qty")
        if c is None:
            continue
        counted += 1
        d = round_qty(float(c) - float(it.get("expected_qty") or 0))
        if d > 0:
            over += 1
            sum_over = round_qty(sum_over + d)
        elif d < 0:
            short += 1
            sum_short = round_qty(sum_short + d)
        else:
            match += 1
    return {"total": total, "counted": counted, "uncounted": total - counted,
            "match": match, "over": over, "short": short,
            "sum_over": sum_over, "sum_short": sum_short}
