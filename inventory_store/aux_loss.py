"""Dashboard HAO HỤT NGUYÊN LIỆU PHỤ — so lượng NL phụ 'dùng cho sản xuất' (lý
thuyết theo công thức) với lượng NL phụ 'sụt giảm thực' đo qua 2 lần KIỂM KHO
liên tiếp của 'kho nguyên liệu đang dùng' (kho đặc biệt aux_source).

Một KỲ = khoảng giữa 2 phiếu kiểm kho ĐÃ CHỐT liên tiếp của kho đó. Với mỗi NL phụ:
  • used  (A) = Σ (số cây THÙNG THÀNH PHẨM tạo trong kỳ × tỉ lệ NL phụ công thức)
  • cham      = NL phụ CHÂM THÊM vào kho trong kỳ (chuyển thùng/nhập NCC/thùng mới,
                theo bút toán đã ghi — bút toán ÂM 'transfer_in/purchase_in/return_in'
                cộng, 'transfer_out' trừ; + thùng mới tạo trong kho)
  • consumed  = đếm_kỳ_trước + cham − đếm_kỳ_này   (tiêu thụ thực, chỉ dựa SỐ ĐẾM)
  • gap       = consumed − used  → dương = mất nhiều hơn định mức (hao hụt thật)

Chỉ dùng SỐ ĐẾM THỰC (actual_quantity) của 2 phiếu, KHÔNG đụng sổ sách hệ thống.
Mốc thời gian chuẩn hoá về epoch UTC (strftime('%s',…)) vì created_at/completed_at
là UTC datetime('now') còn allocated_at là ISO giờ VN (+07:00). Phạm vi = NL phụ
(ingredient có aux=1 trong công thức). Nối: box_allocations, inventory_boxes,
inventory_stocktakes, recipe_store (list_recipe), product_store (resolve_code).
"""
from __future__ import annotations

from .queries import aux_source_place

_CHAM_KINDS = ("transfer_in", "transfer_out", "purchase_in", "return_in")


def _r3(x) -> float:
    return round(float(x or 0), 3)


def combine_material_row(used, cham, prev, now) -> dict:
    """Ghép 1 dòng NL phụ (thuần, không IO). now=None → kỳ ĐANG diễn ra (chưa kiểm
    kho lần sau) nên chỉ có used/cham, consumed/gap để None."""
    used, cham, prev = float(used or 0), float(cham or 0), float(prev or 0)
    if now is None:
        return {"used": _r3(used), "cham": _r3(cham), "prev": _r3(prev),
                "now": None, "consumed": None, "gap": None}
    now = float(now)
    consumed = prev + cham - now
    return {"used": _r3(used), "cham": _r3(cham), "prev": _r3(prev),
            "now": _r3(now), "consumed": _r3(consumed), "gap": _r3(consumed - used)}


def _mat(conn, code, cache: dict) -> dict:
    """Mã NL → danh tính bất biến (product_id) + nhãn hiển thị hiện hành. Cache theo mã."""
    c = str(code or "").strip().upper()
    if c in cache:
        return cache[c]
    from product_store import resolve_code
    p = resolve_code(conn, c)
    info = {
        "key": p["id"] if p else "C:" + c,
        "code": p["code"] if p else c,
        "name": (p.get("name") if p else "") or (p["code"] if p else c),
        "unit": ((p.get("unit") if p else None) or "cây"),
    }
    cache[c] = info
    return info


def _production_usage(conn, t0, t1, cache: dict) -> tuple[dict, dict]:
    """A: NL phụ CẦN theo công thức cho thùng thành phẩm tạo trong (t0, t1].
    Trả ({mat_key: amount}, {mat_key: disp}). Chỉ NL phụ (list_recipe aux=True)."""
    from recipe_store import list_recipe
    rows = conn.execute(
        "SELECT COALESCE(pr.code, b.product_code) AS code, SUM(b.quantity) AS qty "
        "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
        "WHERE b.source_thread_id IS NOT NULL "
        "AND strftime('%s', b.created_at) >  strftime('%s', ?) "
        "AND strftime('%s', b.created_at) <= strftime('%s', ?) "
        "GROUP BY code",
        (t0, t1),
    ).fetchall()
    out: dict = {}
    disp: dict = {}
    for r in rows:
        qty = float(r["qty"] or 0)
        if qty <= 0:
            continue
        for ln in list_recipe(conn, r["code"], aux=True):
            info = _mat(conn, ln["ingredient_code"], cache)
            k = info["key"]
            disp[k] = info
            out[k] = out.get(k, 0.0) + float(ln["ratio"] or 0) * qty
    return out, disp


def _cham(conn, place_id, t0, t1, cache: dict) -> tuple[dict, dict]:
    """Châm THÊM NL phụ vào kho trong (t0, t1]: bút toán chuyển/nhập (−quantity) +
    thùng MỚI tạo trong kho (quantity). Trả ({mat_key: net_inflow}, disp)."""
    out: dict = {}
    disp: dict = {}
    qmarks = ",".join("?" * len(_CHAM_KINDS))
    for r in conn.execute(
        "SELECT COALESCE(pr.code, b.product_code) AS code, SUM(-a.quantity) AS inflow "
        "FROM box_allocations a JOIN inventory_boxes b ON b.id = a.box_id "
        "LEFT JOIN products pr ON pr.id = b.product_id "
        f"WHERE b.place_id = ? AND a.kind IN ({qmarks}) "
        "AND strftime('%s', a.allocated_at) >  strftime('%s', ?) "
        "AND strftime('%s', a.allocated_at) <= strftime('%s', ?) "
        "GROUP BY code",
        (place_id, *_CHAM_KINDS, t0, t1),
    ).fetchall():
        info = _mat(conn, r["code"], cache)
        disp[info["key"]] = info
        out[info["key"]] = out.get(info["key"], 0.0) + float(r["inflow"] or 0)
    for r in conn.execute(
        "SELECT COALESCE(pr.code, b.product_code) AS code, SUM(b.quantity) AS q "
        "FROM inventory_boxes b LEFT JOIN products pr ON pr.id = b.product_id "
        "WHERE b.place_id = ? "
        "AND strftime('%s', b.created_at) >  strftime('%s', ?) "
        "AND strftime('%s', b.created_at) <= strftime('%s', ?) "
        "GROUP BY code",
        (place_id, t0, t1),
    ).fetchall():
        info = _mat(conn, r["code"], cache)
        disp[info["key"]] = info
        out[info["key"]] = out.get(info["key"], 0.0) + float(r["q"] or 0)
    return out, disp


def _counts(conn, stocktake_id, cache: dict) -> tuple[dict, dict]:
    """Số ĐẾM THỰC của 1 phiếu kiểm kho theo NL (SUM actual_quantity)."""
    if not stocktake_id:
        return {}, {}
    out: dict = {}
    disp: dict = {}
    for r in conn.execute(
        "SELECT product_code AS code, SUM(actual_quantity) AS cnt "
        "FROM inventory_stocktake_items "
        "WHERE stocktake_id = ? AND actual_quantity IS NOT NULL GROUP BY product_code",
        (stocktake_id,),
    ).fetchall():
        info = _mat(conn, r["code"], cache)
        disp[info["key"]] = info
        out[info["key"]] = out.get(info["key"], 0.0) + float(r["cnt"] or 0)
    return out, disp


def _build_period(conn, place_id, aux_ids, *, prev_id, t0, prev_ts, cur_id, t1, cur_ts, open_, cache) -> dict:
    used, d1 = _production_usage(conn, t0, t1, cache)
    cham, d2 = _cham(conn, place_id, t0, t1, cache)
    prev_c, d3 = _counts(conn, prev_id, cache)
    now_c, d4 = ({}, {}) if open_ else _counts(conn, cur_id, cache)
    disp = {**d1, **d2, **d3, **d4}
    # Phạm vi = NL phụ: key phải là product_id nằm trong tập ingredient aux=1.
    keys = {k for k in (set(used) | set(cham) | set(prev_c) | set(now_c))
            if isinstance(k, int) and k in aux_ids}
    rows = []
    tot_used = tot_cham = tot_cons = tot_gap = 0.0
    for k in keys:
        row = combine_material_row(used.get(k, 0), cham.get(k, 0),
                                   prev_c.get(k, 0), None if open_ else now_c.get(k, 0))
        info = disp.get(k, {})
        row["code"] = info.get("code", str(k))
        row["name"] = info.get("name", "")
        row["unit"] = info.get("unit", "cây")
        rows.append(row)
        tot_used += row["used"]
        tot_cham += row["cham"]
        if row["consumed"] is not None:
            tot_cons += row["consumed"]
            tot_gap += row["gap"]
    # Nặng nhất (hao hụt lớn) lên đầu; kỳ mở xếp theo lượng dùng.
    rows.sort(key=lambda r: (r["gap"] if r["gap"] is not None else r["used"]), reverse=True)
    return {
        "open": open_,
        "prev_id": prev_id, "prev_at": t0, "prev_ts": prev_ts,
        "cur_id": cur_id, "cur_at": None if open_ else t1, "cur_ts": None if open_ else cur_ts,
        "rows": rows,
        "totals": {
            "used": _r3(tot_used), "cham": _r3(tot_cham),
            "consumed": None if open_ else _r3(tot_cons),
            "gap": None if open_ else _r3(tot_gap),
        },
    }


def aux_loss_periods(conn, *, limit: int = 30, include_open: bool = True) -> dict:
    """Danh sách KỲ (mới → cũ) so NL phụ dùng-cho-SX vs sụt-giảm-kiểm-kho.
    limit = số kỳ ĐÃ CHỐT gần nhất; include_open = kèm kỳ đang diễn ra (chỉ có used/cham)."""
    place = aux_source_place(conn)
    if not place:
        return {"place": None, "periods": [], "error": "no_aux_place"}
    place_id = int(place["id"])
    aux_ids = {int(r[0]) for r in conn.execute(
        "SELECT DISTINCT ingredient_id FROM product_recipes "
        "WHERE COALESCE(aux, 0) = 1 AND ingredient_id IS NOT NULL"
    ).fetchall()}
    stk = conn.execute(
        "SELECT id, completed_at, CAST(strftime('%s', completed_at) AS INTEGER) AS ts "
        "FROM inventory_stocktakes "
        "WHERE place_id = ? AND status = 'completed' AND completed_at IS NOT NULL "
        "ORDER BY strftime('%s', completed_at), id",
        (place_id,),
    ).fetchall()
    cache: dict = {}
    periods: list = []
    pairs = [(stk[i - 1], stk[i]) for i in range(1, len(stk))]
    for prev, cur in reversed(pairs[-max(1, int(limit)):] if pairs else []):
        periods.append(_build_period(
            conn, place_id, aux_ids, prev_id=int(prev["id"]), t0=prev["completed_at"], prev_ts=prev["ts"],
            cur_id=int(cur["id"]), t1=cur["completed_at"], cur_ts=cur["ts"], open_=False, cache=cache))
    if include_open and stk:
        last = stk[-1]
        periods.insert(0, _build_period(
            conn, place_id, aux_ids, prev_id=int(last["id"]), t0=last["completed_at"], prev_ts=last["ts"],
            cur_id=None, t1="now", cur_ts=None, open_=True, cache=cache))
    return {"place": {"id": place_id, "name": place["name"]}, "periods": periods}
