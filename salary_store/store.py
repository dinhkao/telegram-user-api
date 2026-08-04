"""Lương THÁNG: phụ cấp/thưởng theo tháng + ứng lương (nhiều lần) — app.db.

2 bảng:
- salary_month(ym, worker_id, phu_cap, thuong, note, monthly_salary, bhxh): 1 dòng/
  (tháng, thợ) — thưởng văn phòng gán theo THÁNG (khác phụ cấp per-phiếu SX ở
  production_allowances) + 2 số đặt-theo-tháng-và-KẾ-THỪA: mốc lương (moc.py) và
  TRỪ BHXH (bhxh.py).
- salary_advances(id, worker_id, ym, amount, adv_date, note, ...): ỨNG lương NHIỀU lần/
  tháng, cộng dồn trừ vào lương. KHÔNG xoá cứng — VÔ HIỆU (voided_at/by/reason): dòng
  giữ nguyên để đối chiếu, totals bỏ qua. salary_allowances (phụ cấp) cùng cơ chế.

compute_month_payroll gộp lương SP (production_store.report_slips.compute_range_report
theo khoảng tháng) + phụ cấp + thưởng − ứng − BHXH = thực lãnh cho MỌI thợ. Thợ 'time'
(lương thời gian) tính từ mốc + chấm công. Nối: utils.db, worker_store, production_store.
"""
from __future__ import annotations

import calendar

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS salary_month (
    ym          TEXT    NOT NULL,          -- 'YYYY-MM'
    worker_id   INTEGER NOT NULL,
    phu_cap     REAL    NOT NULL DEFAULT 0,
    thuong      REAL    NOT NULL DEFAULT 0,
    note        TEXT    DEFAULT '',
    updated_at  TEXT    DEFAULT (datetime('now', '+7 hours')),
    updated_by  TEXT    DEFAULT '',
    UNIQUE(ym, worker_id)
);
CREATE TABLE IF NOT EXISTS salary_advances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id   INTEGER NOT NULL,
    ym          TEXT    NOT NULL,          -- tháng tính ứng vào 'YYYY-MM'
    amount      REAL    NOT NULL DEFAULT 0,
    adv_date    TEXT    DEFAULT '',         -- ngày ứng 'YYYY-MM-DD'
    note        TEXT    DEFAULT '',
    created_by  TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now', '+7 hours'))
);
CREATE TABLE IF NOT EXISTS salary_allowances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id   INTEGER NOT NULL,
    ym          TEXT    NOT NULL,          -- tháng tính phụ cấp vào 'YYYY-MM'
    amount      REAL    NOT NULL DEFAULT 0,
    note        TEXT    DEFAULT '',         -- nhãn khoản phụ cấp (ăn trưa, xăng xe…)
    created_by  TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now', '+7 hours'))
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_salary_month_ym ON salary_month(ym)",
    "CREATE INDEX IF NOT EXISTS idx_salary_adv ON salary_advances(ym, worker_id)",
    "CREATE INDEX IF NOT EXISTS idx_salary_allow ON salary_allowances(ym, worker_id)",
]


def ensure_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(salary_month)").fetchall()}
    if "weekly" not in cols:   # nhận lương tuần THEO THÁNG (riêng bảng lương, không phải hồ sơ thợ)
        conn.execute("ALTER TABLE salary_month ADD COLUMN weekly INTEGER DEFAULT 0")
    if "monthly_salary" not in cols:
        # MỐC lương tháng đặt RIÊNG từng tháng (NULL = tháng đó kế thừa mốc gần nhất
        # trước đó / mốc hồ sơ thợ) — luật ở salary_store/moc.py
        conn.execute("ALTER TABLE salary_month ADD COLUMN monthly_salary REAL")
    # 2 cờ THƯỞNG bật/tắt theo tháng (KHÔNG kế thừa — xem salary_store/bonus.py)
    for flag in ("thuong_cc", "thuong_vs"):
        if flag not in cols:
            conn.execute(f"ALTER TABLE salary_month ADD COLUMN {flag} INTEGER DEFAULT 0")
    if "bhxh" not in cols:
        # TRỪ BHXH hằng tháng, cũng đặt RIÊNG từng tháng + kế thừa (NULL = tháng đó
        # không đặt riêng, KHÁC 0 = đặt riêng bằng 0) — luật ở salary_store/bhxh.py
        conn.execute("ALTER TABLE salary_month ADD COLUMN bhxh REAL")
    # PHỤ CẤP theo CÔNG THỨC: calc_kind ('pct'/'day'/NULL) + calc_value (% hoặc đơn
    # giá/ngày). NULL = khoản tiền cố định như cũ — xem salary_store/allowance_calc.py
    acols = {r[1] for r in conn.execute("PRAGMA table_info(salary_allowances)").fetchall()}
    if "calc_kind" not in acols:
        conn.execute("ALTER TABLE salary_allowances ADD COLUMN calc_kind TEXT")
        conn.execute("ALTER TABLE salary_allowances ADD COLUMN calc_value REAL")
    # vô hiệu hoá thay cho xoá (giữ dòng đối chiếu): ai + lúc nào + lý do
    for table in ("salary_advances", "salary_allowances"):
        tcols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "voided_at" not in tcols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN voided_at TEXT")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN voided_by TEXT DEFAULT ''")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN void_reason TEXT DEFAULT ''")
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def month_range(ym: str) -> tuple[str, str]:
    """'2026-07' → ('2026-07-01', '2026-07-31')."""
    y, m = (int(x) for x in ym.split("-")[:2])
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


# ── Phụ cấp / thưởng theo tháng ─────────────────────────────────────────────────

def get_month_adjust(conn, ym: str) -> dict:
    """{worker_id: {'thuong', 'note', 'weekly', 'thuong_cc', 'thuong_vs'}} của 1 tháng.
    (Phụ cấp giờ là NHIỀU KHOẢN ở salary_allowances — xem allowance_rows_by_worker; thuong_cc/
    thuong_vs là 2 CỜ bật/tắt thưởng, số tiền tính ở salary_store/bonus.py.)"""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_id, thuong, note, weekly, thuong_cc, thuong_vs FROM salary_month WHERE ym = ?", (ym,)
    ).fetchall()
    return {r["worker_id"]: {"thuong": float(r["thuong"] or 0),
                             "note": r["note"] or "", "weekly": bool(r["weekly"]),
                             "thuong_cc": bool(r["thuong_cc"]), "thuong_vs": bool(r["thuong_vs"])}
            for r in rows}


def set_month_adjust(conn, ym: str, worker_id: int, *, thuong=None, note=None,
                     weekly=None, thuong_cc=None, thuong_vs=None, by: str = "") -> None:
    """Cập nhật thưởng/ghi chú/nhận-lương-tuần/2 cờ THƯỞNG của 1 (tháng, thợ). Field
    None = giữ nguyên. weekly = nhận lương tuần THEO THÁNG (riêng bảng lương, không
    phải hồ sơ thợ); thuong_cc/thuong_vs = bật thưởng chuyên cần / vệ sinh của tháng
    đó (số tiền tính live ở salary_store/bonus.py, KHÔNG kế thừa sang tháng sau).
    Phụ cấp KHÔNG ở đây nữa — dùng add_allowance (nhiều khoản)."""
    ensure_schema(conn)
    with transaction(conn):
        cur = conn.execute(
            "SELECT thuong, note, weekly, thuong_cc, thuong_vs FROM salary_month "
            "WHERE ym = ? AND worker_id = ?", (ym, worker_id),
        ).fetchone()
        th = float(cur["thuong"] or 0) if cur else 0.0
        nt = (cur["note"] or "") if cur else ""
        wk = int(cur["weekly"] or 0) if cur else 0
        cc = int(cur["thuong_cc"] or 0) if cur else 0
        vs = int(cur["thuong_vs"] or 0) if cur else 0
        if thuong is not None:
            th = max(0.0, float(thuong))
        if note is not None:
            nt = str(note)
        if weekly is not None:
            wk = 1 if weekly else 0
        if thuong_cc is not None:
            cc = 1 if thuong_cc else 0
        if thuong_vs is not None:
            vs = 1 if thuong_vs else 0
        conn.execute(
            "INSERT INTO salary_month (ym, worker_id, thuong, note, weekly, thuong_cc, thuong_vs, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','+7 hours'), ?) "
            "ON CONFLICT(ym, worker_id) DO UPDATE SET thuong=excluded.thuong, "
            "note=excluded.note, weekly=excluded.weekly, thuong_cc=excluded.thuong_cc, "
            "thuong_vs=excluded.thuong_vs, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (ym, worker_id, th, nt, wk, cc, vs, by or ""),
        )


# ── Ứng lương (nhiều lần / tháng) ────────────────────────────────────────────────

def list_advances(conn, ym: str, worker_id: int | None = None) -> list[dict]:
    ensure_schema(conn)
    q = ("SELECT id, worker_id, ym, amount, adv_date, note, created_by, created_at, "
         "voided_at, voided_by, void_reason FROM salary_advances WHERE ym = ?")
    args: list = [ym]
    if worker_id is not None:
        q += " AND worker_id = ?"
        args.append(worker_id)
    q += " ORDER BY adv_date ASC, id ASC"
    return [{"id": r["id"], "worker_id": r["worker_id"], "ym": r["ym"], "amount": float(r["amount"] or 0),
             "adv_date": r["adv_date"] or "", "note": r["note"] or "", "created_by": r["created_by"] or "",
             "created_at": r["created_at"] or "", "voided_at": r["voided_at"] or "",
             "voided_by": r["voided_by"] or "", "void_reason": r["void_reason"] or ""}
            for r in conn.execute(q, args).fetchall()]


def advance_totals(conn, ym: str) -> dict:
    """{worker_id: (tổng ứng, số lần)} của 1 tháng."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_id, COALESCE(SUM(amount),0) AS s, COUNT(*) AS c FROM salary_advances "
        "WHERE ym = ? AND voided_at IS NULL GROUP BY worker_id", (ym,)
    ).fetchall()
    return {r["worker_id"]: (float(r["s"] or 0), int(r["c"])) for r in rows}


def add_advance(conn, worker_id: int, ym: str, amount: float, adv_date: str = "",
                note: str = "", by: str = "") -> dict:
    ensure_schema(conn)
    amt = float(amount or 0)
    if amt <= 0:
        raise ValueError("Số tiền ứng phải > 0")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO salary_advances (worker_id, ym, amount, adv_date, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (worker_id, ym, amt, (adv_date or "").strip(), (note or "").strip(), by or ""),
        )
        aid = cur.lastrowid
    return {"id": aid, "worker_id": worker_id, "ym": ym, "amount": amt,
            "adv_date": (adv_date or "").strip(), "note": (note or "").strip()}


def _set_note(conn, table: str, row_id: int, note: str) -> bool:
    """Sửa GHI CHÚ 1 dòng (ứng / phụ cấp). SỐ TIỀN bất biến — ghi nhầm tiền thì VÔ
    HIỆU rồi ghi lại, ghi chú chỉ là nhãn nên sửa thoải mái. Dòng ĐÃ VÔ HIỆU khoá
    (giữ nguyên để đối chiếu). Trả False nếu không có dòng / đã vô hiệu."""
    with transaction(conn):
        cur = conn.execute(
            f"UPDATE {table} SET note = ? WHERE id = ? AND voided_at IS NULL",
            ((note or "").strip(), row_id),
        )
        return cur.rowcount > 0


def update_advance_note(conn, advance_id: int, note: str) -> bool:
    """Sửa ghi chú 1 lần ứng (số tiền/ngày không đổi). Xem _set_note."""
    ensure_schema(conn)
    return _set_note(conn, "salary_advances", advance_id, note)


def void_advance(conn, advance_id: int, reason: str, by: str = "") -> bool:
    """Vô hiệu 1 lần ứng (không xoá dòng — giữ để đối chiếu). Lý do BẮT BUỘC.
    Trả False nếu không tìm thấy hoặc đã vô hiệu rồi."""
    ensure_schema(conn)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Phải nhập lý do vô hiệu")
    with transaction(conn):
        cur = conn.execute(
            "UPDATE salary_advances SET voided_at = datetime('now','+7 hours'), "
            "voided_by = ?, void_reason = ? WHERE id = ? AND voided_at IS NULL",
            (by or "", reason, advance_id),
        )
        return cur.rowcount > 0


# ── Phụ cấp (NHIỀU KHOẢN / tháng, giống ứng lương) ──────────────────────────────

def list_allowances(conn, ym: str, worker_id: int | None = None, *,
                    base: float | None = None, cong: float | None = None) -> list[dict]:
    """Các khoản phụ cấp của tháng. Truyền base/cong (lương gốc + ngày công của thợ)
    thì khoản có CÔNG THỨC được TÍNH LẠI theo số hiện tại — không truyền thì trả số
    chụp lúc nhập (chỉ dùng để hiển thị tạm)."""
    from salary_store.allowance_calc import allowance_amount, calc_label
    ensure_schema(conn)
    q = ("SELECT id, worker_id, ym, amount, note, created_by, created_at, "
         "voided_at, voided_by, void_reason, calc_kind, calc_value FROM salary_allowances WHERE ym = ?")
    args: list = [ym]
    if worker_id is not None:
        q += " AND worker_id = ?"
        args.append(worker_id)
    q += " ORDER BY id ASC"
    out = []
    for r in conn.execute(q, args).fetchall():
        kind, val = r["calc_kind"], r["calc_value"]
        amt = (allowance_amount(kind, val, r["amount"], base=base or 0, cong=cong or 0)
               if (kind and base is not None) else float(r["amount"] or 0))
        out.append({"id": r["id"], "worker_id": r["worker_id"], "ym": r["ym"], "amount": amt,
                    "note": r["note"] or "", "created_by": r["created_by"] or "",
                    "created_at": r["created_at"] or "", "voided_at": r["voided_at"] or "",
                    "voided_by": r["voided_by"] or "", "void_reason": r["void_reason"] or "",
                    "calc_kind": kind or "", "calc_value": float(val) if val is not None else 0,
                    "calc_label": calc_label(kind, val)})
    return out


def allowance_rows_by_worker(conn, ym: str) -> dict:
    """{worker_id: [(calc_kind, calc_value, amount)]} — các khoản CÒN HIỆU LỰC của
    tháng, chưa quy ra tiền. Phải để chỗ gọi tự quy vì khoản theo CÔNG THỨC cần lương
    gốc + ngày công của CHÍNH thợ đó (xem salary_store/allowance_calc.py)."""
    ensure_schema(conn)
    out: dict = {}
    for r in conn.execute(
        "SELECT worker_id, calc_kind, calc_value, amount FROM salary_allowances "
        "WHERE ym = ? AND voided_at IS NULL", (ym,)
    ).fetchall():
        out.setdefault(r["worker_id"], []).append((r["calc_kind"], r["calc_value"], r["amount"]))
    return out


def add_allowance(conn, worker_id: int, ym: str, amount: float, note: str = "", by: str = "",
                  calc_kind: str | None = None, calc_value=None) -> dict:
    """Thêm 1 khoản phụ cấp. calc_kind='pct'/'day' + calc_value = CÔNG THỨC (%, hoặc
    đơn giá 1 ngày công) → số tiền sẽ được tính lại theo lương gốc mỗi lần xem;
    `amount` khi đó chỉ là số chụp lúc nhập. Không có công thức = tiền cố định."""
    from salary_store.allowance_calc import normalize
    ensure_schema(conn)
    kind, val = normalize(calc_kind, calc_value)
    amt = float(amount or 0)
    # khoản theo công thức: gốc tháng này có thể đang = 0 (chưa có báo cáo/chấm công)
    # → cho phép amount 0, số thật tính sau; khoản cố định thì vẫn bắt buộc > 0
    if amt <= 0 and not kind:
        raise ValueError("Số tiền phụ cấp phải > 0")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO salary_allowances (worker_id, ym, amount, note, created_by, calc_kind, calc_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (worker_id, ym, max(0.0, amt), (note or "").strip(), by or "", kind, val),
        )
        aid = cur.lastrowid
    return {"id": aid, "worker_id": worker_id, "ym": ym, "amount": amt,
            "note": (note or "").strip(), "calc_kind": kind or "", "calc_value": val or 0}


def update_allowance_note(conn, allowance_id: int, note: str) -> bool:
    """Sửa nhãn/ghi chú 1 khoản phụ cấp (số tiền không đổi). Xem _set_note."""
    ensure_schema(conn)
    return _set_note(conn, "salary_allowances", allowance_id, note)


def void_allowance(conn, allowance_id: int, reason: str, by: str = "") -> bool:
    """Vô hiệu 1 khoản phụ cấp (không xoá dòng). Lý do BẮT BUỘC. Cùng cơ chế void_advance."""
    ensure_schema(conn)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Phải nhập lý do vô hiệu")
    with transaction(conn):
        cur = conn.execute(
            "UPDATE salary_allowances SET voided_at = datetime('now','+7 hours'), "
            "voided_by = ?, void_reason = ? WHERE id = ? AND voided_at IS NULL",
            (by or "", reason, allowance_id),
        )
        return cur.rowcount > 0


# ── Bảng lương tháng (tính live) ─────────────────────────────────────────────────

def compute_month_payroll(conn, ym: str) -> dict:
    """Bảng lương 1 tháng cho MỌI thợ. 3 loại `wage_type`:
    - 'product' (SP): lương SP tự tính từ sản xuất (ĐÃ GỒM phụ cấp ghi trong phiếu SX —
      production_allowances; trả riêng `pc_phieu` để UI tách cho thấy, KHÁC cột phụ cấp
      tháng `phu_cap` = salary_allowances);
    - 'time' (TG): mốc/26 × ngày công + tăng ca ×1,2 (tính riêng);
    - 'time_flat' (TG*): CỐ ĐỊNH theo ngày công, giờ tăng ca GỘP LUÔN vào ngày công →
      `cong` đã gồm TC, `luong_tc` = 0 (`ot_gio` vẫn trả để biết đã gộp bao nhiêu).
    Công/TC quy từ máy chấm công (attendance_store.month_worker_stats); mọi loại rồi
    + phụ cấp + thưởng (gồm 2 khoản bật/tắt: CHUYÊN CẦN cố định + VỆ SINH theo ngày
    công, salary_store.bonus) − ứng − BHXH = thực lãnh.
    Mốc lấy theo TỪNG THÁNG (salary_store.moc: bản đặt gần nhất ≤ ym, chưa
    có thì mốc hồ sơ thợ) nên sửa mốc không tính lại tháng cũ; TRỪ BHXH cũng theo từng
    tháng + kế thừa y hệt (salary_store.bhxh), chưa đặt bao giờ = 0.
    Trả {ym, workers:[...], totals:{...}}."""
    from worker_store import list_workers
    from production_store.report_slips import compute_range_report
    from salary_store.bhxh import month_bhxh_map
    from salary_store.allowance_calc import allowance_amount
    from salary_store.bonus import bonus_amounts
    from salary_store.moc import month_moc_map

    ensure_schema(conn)
    workers = list_workers(conn)
    mstart, mend = month_range(ym)
    product_ids = [w["id"] for w in workers if (w.get("wage_type") or "product") == "product"]
    # (tiền, phụ cấp phiếu SX ĐÃ GỘP trong tiền đó) theo tên thợ hiện hành
    wage_by_name: dict = {}
    if product_ids:
        rep = compute_range_report(conn, mstart, mend, worker_ids=product_ids)
        for w in rep["workers"]:
            wage_by_name[(w.get("name") or "").strip().casefold()] = (
                float(w.get("money") or 0), float(w.get("allowance") or 0))
    # công + tăng ca theo thợ từ máy chấm công (đã gộp sửa tay)
    import attendance_store
    attendance_store.ensure_schema(conn)
    att = attendance_store.month_worker_stats(conn, ym)
    adjust = get_month_adjust(conn, ym)
    moc = month_moc_map(conn, ym)        # mốc lương HIỆU LỰC của tháng này (theo từng tháng)
    bh = month_bhxh_map(conn, ym)        # TRỪ BHXH hiệu lực của tháng này (cùng luật kế thừa)
    adv = advance_totals(conn, ym)
    allow_rows = allowance_rows_by_worker(conn, ym)   # phụ cấp NHIỀU KHOẢN (chưa quy tiền)

    out = []
    tot = {"luong": 0.0, "phu_cap": 0.0, "thuong": 0.0, "thuong_cc": 0.0, "thuong_vs": 0.0,
           "ung": 0.0, "bhxh": 0.0, "thuc_lanh": 0.0}
    for w in workers:
        wid, wt = w["id"], (w.get("wage_type") or "product")
        # mốc tháng (lương TG mong muốn): bản đặt gần nhất ≤ ym; chưa đặt bao giờ thì
        # lùi về mốc hồ sơ thợ (dữ liệu cũ trước khi mốc tách theo tháng)
        mc = moc.get(wid)
        base = float(mc["value"]) if mc else float(w.get("monthly_salary") or 0)
        st = att.get(wid, {})
        work_min, ot_min = int(st.get("work_min") or 0), int(st.get("ot_min") or 0)
        # TG* ('time_flat'): giờ TĂNG CA GỘP THẲNG vào ngày công (trả cố định theo công,
        # KHÔNG có tiền tăng ca ×1,2 riêng). TG ('time') giữ nguyên: công tách, TC ×1,2.
        ot_in_cong = wt == "time_flat"
        cong = (work_min + (ot_min if ot_in_cong else 0)) / 480.0   # ngày đủ 2 ca = 1 công
        # SỐ CÔNG DÙNG ĐỂ NHÂN TIỀN = đúng số IN RA BẢNG (làm tròn 2 số lẻ). Nhân với
        # công thô thì "12.000đ × 2,41 công" người ta bấm máy tính ra 28.920đ mà bảng
        # trả 28.900đ — cùng nguyên tắc "cộng dồn số đã làm tròn" ở dòng TỔNG bên dưới.
        cong_hien = round(cong, 2)
        luong_cong = luong_tc = 0.0
        pc_phieu = 0.0            # phụ cấp PHIẾU SX đã gộp trong lương SP (để UI tách ra)
        if wt == "product":
            luong, pc_phieu = wage_by_name.get(w["name"].strip().casefold(), (0.0, 0.0))
        else:
            # lương TG = lương CÔNG (mốc/26 × công) + lương TĂNG CA (giờ TC ×1,2).
            # TG*: `cong` đã gồm giờ TC ở trên → chỉ có lương công, luong_tc = 0.
            day_rate = base / 26.0
            luong_cong = day_rate * cong
            if not ot_in_cong:
                luong_tc = day_rate * 1.2 * ot_min / 480.0
            luong = luong_cong + luong_tc
        a = adjust.get(wid, {})
        thuong, note = a.get("thuong", 0.0), a.get("note", "")
        # PHỤ CẤP: khoản theo CÔNG THỨC quy ra tiền theo lương gốc của CHÍNH thợ này
        # (thợ SP → lương sản phẩm · thợ TG → lương ngày công, không gồm tăng ca) và
        # số ngày công của tháng → sửa báo cáo/chấm công là phụ cấp tự chạy theo.
        pc_base = luong if wt == "product" else luong_cong
        rows_pc = allow_rows.get(wid, [])
        phu_cap = sum(allowance_amount(k, v, amt, base=pc_base, cong=cong_hien) for k, v, amt in rows_pc)
        pc_count = len(rows_pc)
        weekly = bool(a.get("weekly"))   # nhận lương tuần THEO THÁNG (riêng bảng lương)
        ung_manual, adv_count = adv.get(wid, (0.0, 0))
        # NHẬN LƯƠNG TUẦN → ứng tự động = đúng lương sản phẩm (đã trả theo tuần trong tháng)
        ung_weekly = luong if weekly else 0.0
        ung = ung_manual + ung_weekly
        # TRỪ BHXH: số hiệu lực tháng này (kế thừa bản gần nhất ≤ ym), chưa đặt = 0
        bhr = bh.get(wid)
        bhxh = float(bhr["value"]) if bhr else 0.0
        # 2 khoản THƯỞNG bật/tắt riêng từng tháng (không kế thừa) — chuyên cần cố
        # định, vệ sinh = đơn giá × ĐÚNG số công đang hiện ở cột Công
        cc_on, vs_on = bool(a.get("thuong_cc")), bool(a.get("thuong_vs"))
        thuong_cc, thuong_vs = bonus_amounts(cong_hien, chuyen_can=cc_on, ve_sinh=vs_on)
        thuc_lanh = luong + phu_cap + thuong + thuong_cc + thuong_vs - ung - bhxh
        out.append({
            "worker_id": wid, "name": w["name"], "wage_type": wt, "weekly": weekly,
            "luong": round(luong), "phu_cap": round(phu_cap), "pc_count": pc_count, "thuong": round(thuong),
            "cc_on": cc_on, "vs_on": vs_on,
            "thuong_cc": round(thuong_cc), "thuong_vs": round(thuong_vs),
            "ung": round(ung), "ung_manual": round(ung_manual), "ung_weekly": round(ung_weekly),
            "adv_count": adv_count, "note": note, "thuc_lanh": round(thuc_lanh),
            "bhxh": round(bhxh),
            # số này ĐẶT ở tháng nào ("" = chưa đặt bao giờ → 0) + có đặt RIÊNG tháng
            # đang xem không → UI nói rõ "kế thừa từ tháng X" (giống mốc lương)
            "bhxh_ym": (bhr["ym"] if bhr else ""), "bhxh_own": bool(bhr and bhr["ym"] == ym),
            "monthly_salary": round(base),
            # mốc này ĐẶT ở tháng nào ("" = mốc hồ sơ thợ) + có phải đặt RIÊNG tháng
            # đang xem không → UI nói rõ "kế thừa từ tháng X" thay vì im lặng
            "moc_ym": (mc["ym"] if mc else ""), "moc_own": bool(mc and mc["ym"] == ym),
            "cong": cong_hien,
            "ot_gio": round(ot_min / 60.0, 1),
            "luong_cong": round(luong_cong), "luong_tc": round(luong_tc),
            # 2 NGUỒN lương tách bạch cho bảng lương khỏi mập mờ: `luong_tg` = lương
            # THỜI GIAN (công + tăng ca), `luong_sp` = lương SẢN PHẨM. Mỗi thợ chỉ ăn
            # 1 trong 2 (theo wage_type) nên luong_tg + luong_sp == luong.
            "luong_tg": round(luong_cong + luong_tc) if wt != "product" else 0,
            "luong_sp": round(luong) if wt == "product" else 0,
            # phụ cấp ghi trong PHIẾU SX (production_allowances) — ĐÃ nằm TRONG `luong`,
            # tách ra để bảng lương nói rõ, đừng cộng lần nữa
            "pc_phieu": round(pc_phieu),
        })
        # Cộng dồn SỐ ĐÃ LÀM TRÒN (đúng số in trên dòng) — cộng float thô rồi
        # round 1 lần làm tổng cột lệch tổng các dòng tới ~N/2 đồng.
        row = out[-1]
        tot["luong"] += row["luong"]
        tot["phu_cap"] += row["phu_cap"]
        tot["thuong"] += row["thuong"]
        tot["thuong_cc"] += row["thuong_cc"]
        tot["thuong_vs"] += row["thuong_vs"]
        tot["ung"] += row["ung"]
        tot["bhxh"] += row["bhxh"]
        tot["thuc_lanh"] += row["thuc_lanh"]
    return {"ym": ym, "workers": out, "totals": {k: round(v) for k, v in tot.items()}}
