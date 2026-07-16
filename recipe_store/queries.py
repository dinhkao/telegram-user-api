"""CRUD công thức (product_recipes) + tính nhu cầu nguyên liệu. IO + transaction.
Danh tính theo product_id/ingredient_id (nhận cả mã cũ qua resolve); mã trả về
luôn là MÃ HIỆN HÀNH. Nối: utils.db, product_store (resolve). Trừ kho thực hiện
ở inventory_store.allocate_picks(kind='production')."""
from __future__ import annotations

from utils.db import transaction


def _code(x) -> str:
    return str(x or "").strip().upper()


def _resolve(conn, code):
    from product_store import resolve_code
    return resolve_code(conn, _code(code))


def list_recipe(conn, product_code, aux: bool | None = None) -> list[dict]:
    """Các nguyên liệu của 1 sản phẩm: [{id, ingredient_id, ingredient_code, ratio, aux}].
    aux=None: mọi dòng; aux=False: chỉ NL CHÍNH; aux=True: chỉ NL PHỤ.
    ingredient_code = mã hiện hành (join products theo id, fallback snapshot)."""
    prod = _resolve(conn, product_code)
    if prod:
        where, params = "(r.product_id = ? OR (r.product_id IS NULL AND r.product_code = ?))", [prod["id"], prod["code"]]
    else:
        where, params = "r.product_code = ?", [_code(product_code)]
    if aux is not None:
        where += " AND COALESCE(r.aux, 0) = ?"
        params.append(1 if aux else 0)
    rows = conn.execute(
        "SELECT r.id, r.ingredient_id, COALESCE(pi.code, r.ingredient_code) AS ingredient_code, "
        "r.ratio, COALESCE(r.aux, 0) AS aux, r.ratio_unit, r.ratio_factor "
        "FROM product_recipes r LEFT JOIN products pi ON pi.id = r.ingredient_id "
        f"WHERE {where} ORDER BY aux, ingredient_code",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def set_recipe_line(conn, product_code, ingredient_code, ratio, aux: bool = False,
                    ratio_unit: str | None = None, ratio_factor=None) -> dict | None:
    """Thêm/sửa 1 nguyên liệu (upsert theo cặp). ratio > 0 — hiểu theo ĐƠN VỊ
    ratio_unit nếu có (1 unit = ratio_factor đơn vị gốc, từ product_units của NL);
    DB luôn lưu ratio quy về GỐC + snapshot unit/factor để hiển thị. Đơn vị xấu
    (factor ≤ 0/không parse) → rơi phần unit, ratio hiểu theo gốc như cũ.
    Không cho tự làm nguyên liệu. aux=True = NGUYÊN LIỆU PHỤ (trừ kho cả phiếu SX
    khi SP bật aux_required); upsert đổi được chính↔phụ. Ghi CẢ id (danh tính) +
    mã hiện hành (snapshot, tự chuẩn hoá khi gõ mã cũ)."""
    prod, ing = _resolve(conn, product_code), _resolve(conn, ingredient_code)
    pc = prod["code"] if prod else _code(product_code)
    ic = ing["code"] if ing else _code(ingredient_code)
    pid = prod["id"] if prod else None
    iid = ing["id"] if ing else None
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return None
    if not pc or not ic or ic == pc or (pid and iid and pid == iid) or r <= 0:
        return None
    ru, rf = None, None
    if ratio_unit and str(ratio_unit).strip():
        try:
            f = float(ratio_factor)
        except (TypeError, ValueError):
            f = 0.0
        if f > 0:
            ru, rf = str(ratio_unit).strip(), f
            r = r * f   # quy về đơn vị gốc — mọi công thức tính giữ nguyên
    a = 1 if aux else 0
    with transaction(conn):
        # Upsert theo DANH TÍNH (id) trước — mã snapshot của dòng cũ có thể chưa
        # refresh sau đổi mã, match theo mã sẽ tạo dòng đôi. Tiện thể refresh snapshot.
        existing = None
        if pid and iid:
            existing = conn.execute(
                "SELECT id FROM product_recipes WHERE product_id = ? AND ingredient_id = ?",
                (pid, iid),
            ).fetchone()
        if existing:
            conn.execute(
                "UPDATE product_recipes SET ratio = ?, product_code = ?, ingredient_code = ?, aux = ?, "
                "ratio_unit = ?, ratio_factor = ? WHERE id = ?",
                (r, pc, ic, a, ru, rf, existing[0]),
            )
            line_id = existing[0]
        else:
            cur = conn.execute(
                "INSERT INTO product_recipes (product_id, ingredient_id, product_code, ingredient_code, ratio, aux, ratio_unit, ratio_factor) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(product_code, ingredient_code) DO UPDATE SET "
                "ratio = excluded.ratio, product_id = excluded.product_id, "
                "ingredient_id = excluded.ingredient_id, aux = excluded.aux, "
                "ratio_unit = excluded.ratio_unit, ratio_factor = excluded.ratio_factor",
                (pid, iid, pc, ic, r, a, ru, rf),
            )
            line_id = cur.lastrowid
    row = conn.execute(
        "SELECT id, ingredient_id, ingredient_code, ratio, COALESCE(aux, 0) AS aux, ratio_unit, ratio_factor "
        "FROM product_recipes WHERE id = ?",
        (line_id,),
    ).fetchone()
    if not row:  # nhánh ON CONFLICT: lastrowid không trỏ dòng update → tra theo cặp mã
        row = conn.execute(
            "SELECT id, ingredient_id, ingredient_code, ratio, COALESCE(aux, 0) AS aux, ratio_unit, ratio_factor "
            "FROM product_recipes WHERE product_code = ? AND ingredient_code = ?",
            (pc, ic),
        ).fetchone()
    return dict(row) if row else None


def delete_recipe_line(conn, line_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM product_recipes WHERE id = ?", (int(line_id),))
    return True


def recipe_needs(conn, product_code, produced_qty, aux: bool | None = None) -> list[dict]:
    """Nhu cầu nguyên liệu khi làm produced_qty cây thành phẩm:
    [{code, amount}] với amount = ratio × produced_qty; code = mã NL hiện hành.
    aux=False: NL CHÍNH (chỉ phiếu ĐÓNG GÓI bắt buộc); aux=True: NL PHỤ (bắt buộc
    CẢ 2 loại phiếu khi products.aux_required bật); None: mọi dòng.
    Rỗng nếu chưa có công thức (validate ở inventory_routes)."""
    q = float(produced_qty or 0)
    if q <= 0:
        return []
    return [
        {"code": r["ingredient_code"], "amount": round(r["ratio"] * q, 3)}
        for r in list_recipe(conn, product_code, aux=aux)
    ]
