"""PHIẾU BÁO CÁO sản xuất (production_report_slips) — app.db.

1 phiếu = 1 khoảng ngày (from_ymd → to_ymd) do văn phòng tạo, tuỳ chọn CHỌN THỢ
(worker_ids JSON — id bất biến production_workers; NULL = mọi thợ); nội dung báo
cáo KHÔNG lưu cứng mà TÍNH LẠI mỗi lần xem từ production_report_rows (tổng SP
từng thợ, tiền công từng phiếu SX, tổng cộng — đơn giá CHỐT theo phiếu luong_1sp
→ fallback production_store.wages + phụ cấp production_store.allowances).
Nối: utils.db, production_report_rows, products, production_workers.
API: server_app/report_slip_routes.
"""
from __future__ import annotations

import json
import re

from utils.db import transaction

_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_report_slips (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_ymd   TEXT NOT NULL,
            to_ymd     TEXT NOT NULL,
            note       TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', '+7 hours'))
        )
        """
    )
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(production_report_slips)").fetchall()}
    if "worker_ids" not in cols:   # JSON [id, ...] thợ được chọn; NULL = mọi thợ
        conn.execute("ALTER TABLE production_report_slips ADD COLUMN worker_ids TEXT")
    conn.commit()


def _row(r) -> dict:
    try:
        wids = json.loads(r["worker_ids"]) if r["worker_ids"] else None
    except (TypeError, ValueError):
        wids = None
    return {
        "id": r["id"], "from_ymd": r["from_ymd"], "to_ymd": r["to_ymd"],
        "note": r["note"] or "", "created_by": r["created_by"] or "",
        "created_at": r["created_at"] or "",
        "worker_ids": wids if isinstance(wids, list) else None,
    }


def list_slips(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, from_ymd, to_ymd, note, created_by, created_at, worker_ids "
        "FROM production_report_slips ORDER BY id DESC"
    ).fetchall()
    return [_row(r) for r in rows]


def get_slip(conn, slip_id: int) -> dict | None:
    r = conn.execute(
        "SELECT id, from_ymd, to_ymd, note, created_by, created_at, worker_ids "
        "FROM production_report_slips WHERE id = ?", (slip_id,)
    ).fetchone()
    return _row(r) if r else None


def add_slip(conn, from_ymd: str, to_ymd: str, note: str = "", by: str = "",
             worker_ids: list[int] | None = None) -> dict:
    f, t = (from_ymd or "").strip(), (to_ymd or "").strip()
    if not _YMD.match(f) or not _YMD.match(t):
        raise ValueError("Phải chọn ngày bắt đầu và ngày kết thúc (YYYY-MM-DD)")
    if f > t:
        raise ValueError("Ngày bắt đầu phải trước (hoặc bằng) ngày kết thúc")
    wids = None
    if worker_ids:
        wids = json.dumps(sorted({int(x) for x in worker_ids}))
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO production_report_slips (from_ymd, to_ymd, note, created_by, worker_ids) "
            "VALUES (?, ?, ?, ?, ?)",
            (f, t, (note or "").strip(), by or "", wids),
        )
        sid = cur.lastrowid
    return get_slip(conn, sid)


def resolve_worker_names(conn, worker_ids: list[int] | None) -> list[str] | None:
    """TÊN HIỆN HÀNH của các thợ đã chọn (id bất biến — đổi tên vẫn khớp).
    None nếu phiếu tính mọi thợ; id đã xoá bị bỏ qua."""
    if not worker_ids:
        return None
    qs = ",".join("?" * len(worker_ids))
    rows = conn.execute(
        f"SELECT name FROM production_workers WHERE id IN ({qs}) "
        "ORDER BY sort_order ASC, name COLLATE NOCASE ASC",
        [int(x) for x in worker_ids],
    ).fetchall()
    return [r["name"] for r in rows]


_KEEP = object()   # sentinel: field không truyền = giữ nguyên


def update_slip(conn, slip_id: int, *, from_ymd=_KEEP, to_ymd=_KEEP, note=_KEEP,
                worker_ids=_KEEP) -> dict | None:
    """Sửa phiếu báo cáo đã tạo (ngày, ghi chú, chọn thợ). Field không truyền giữ
    nguyên; worker_ids=None = MỌI THỢ, list = chỉ các thợ đó. Trả slip mới/None."""
    cur = get_slip(conn, slip_id)
    if not cur:
        return None
    f = cur["from_ymd"] if from_ymd is _KEEP else str(from_ymd or "").strip()
    t = cur["to_ymd"] if to_ymd is _KEEP else str(to_ymd or "").strip()
    if not _YMD.match(f) or not _YMD.match(t):
        raise ValueError("Phải chọn ngày bắt đầu và ngày kết thúc (YYYY-MM-DD)")
    if f > t:
        raise ValueError("Ngày bắt đầu phải trước (hoặc bằng) ngày kết thúc")
    n = cur["note"] if note is _KEEP else (str(note or "")).strip()
    if worker_ids is _KEEP:
        wids = json.dumps(cur["worker_ids"]) if cur["worker_ids"] else None
    elif worker_ids:
        wids = json.dumps(sorted({int(x) for x in worker_ids}))
    else:
        wids = None   # mọi thợ
    with transaction(conn):
        conn.execute(
            "UPDATE production_report_slips SET from_ymd = ?, to_ymd = ?, note = ?, worker_ids = ? "
            "WHERE id = ?",
            (f, t, n, wids, slip_id),
        )
    return get_slip(conn, slip_id)


def delete_slip(conn, slip_id: int) -> bool:
    with transaction(conn):
        cur = conn.execute("DELETE FROM production_report_slips WHERE id = ?", (slip_id,))
        return cur.rowcount > 0


# ── Nội dung báo cáo (tính live) ────────────────────────────────────────────────

def compute_range_report(conn, dfrom: str, dto: str, worker_ids: list[int] | None = None) -> dict:
    """Báo cáo 1 khoảng ngày: THEO THỢ (tổng SP + tiền, breakdown theo mã SP) +
    THEO PHIẾU SX (mỗi phiếu: ngày, mã SP, số SP, tiền công) + TỔNG CỘNG.
    Tiền = số cây × ĐƠN GIÁ CHỐT THEO PHIẾU (production_slips.luong_1sp; NULL =
    chưa chốt → bảng lương hiện tại) + phụ cấp (gắn 1 lần / (phiếu, thợ)).
    worker_ids: CHỈ TÍNH các thợ này (khớp theo tên hiện hành); None = mọi thợ."""
    from production_store.wages import wage_per_cay

    only_names = resolve_worker_names(conn, worker_ids)   # None = không lọc
    only_cf = {n.strip().casefold() for n in only_names} if only_names is not None else None

    rows = conn.execute(
        "SELECT t.thread_id AS tid, t.report_ymd AS ymd, t.worker_name AS wname, "
        "COALESCE(w.name, t.worker_name) AS worker, COALESCE(pr.code, t.product_code) AS code, "
        "ROUND(SUM(t.tong_calc), 1) AS cay, s.luong_1sp AS slip_wage "
        "FROM production_report_rows t "
        "LEFT JOIN production_workers w ON w.id = t.worker_id "
        "LEFT JOIN products pr ON pr.id = t.product_id "
        "LEFT JOIN production_slips s ON s.thread_id = t.thread_id "
        "WHERE t.report_ymd IS NOT NULL AND t.report_ymd >= ? AND t.report_ymd <= ? "
        # GROUP BY biểu thức đầy đủ — tên trần "code" bị SQLite resolve về pr.code (NULL
        # khi chưa gán product_id) làm các mã SP gộp nhầm làm một
        "GROUP BY t.thread_id, t.worker_name, COALESCE(w.name, t.worker_name), "
        "         COALESCE(pr.code, t.product_code) "
        "ORDER BY t.report_ymd ASC, t.thread_id ASC",
        (dfrom, dto),
    ).fetchall()

    # Phụ cấp của các phiếu trong khoảng — khoá (thread_id, tên thợ snapshot)
    tids = sorted({r["tid"] for r in rows})
    allow: dict[tuple, float] = {}
    if tids:
        qs = ",".join("?" * len(tids))
        for a in conn.execute(
            f"SELECT thread_id, worker_name, amount FROM production_allowances WHERE thread_id IN ({qs})",
            tids,
        ).fetchall():
            allow[(a["thread_id"], a["worker_name"])] = float(a["amount"] or 0)

    workers: dict[str, dict] = {}
    phieus: dict[int, dict] = {}
    missing: set = set()
    allow_used: set = set()   # (tid, wname) đã cộng phụ cấp — chỉ cộng 1 lần

    for r in rows:
        tid, ymd, wname = r["tid"], r["ymd"], r["wname"]
        worker, code, cay = (r["worker"] or "?"), (r["code"] or ""), float(r["cay"] or 0)
        if only_cf is not None and worker.strip().casefold() not in only_cf:
            continue   # phiếu báo cáo chỉ tính các thợ đã chọn
        # đơn giá CHỐT theo phiếu; chưa chốt (NULL) → bảng lương hiện tại
        wage = float(r["slip_wage"]) if r["slip_wage"] is not None else wage_per_cay(code)
        if cay > 0 and wage <= 0:
            missing.add(code)
        piece = round(cay * wage)
        a = 0
        if (tid, wname) not in allow_used:
            a = round(allow.get((tid, wname), 0))
            allow_used.add((tid, wname))
        money = piece + a

        wk = workers.setdefault(worker, {"name": worker, "cay": 0.0, "money": 0, "allowance": 0, "items": {}, "days": {}})
        # item gộp theo (mã, đơn giá) — phiếu chốt giá khác nhau không trộn 1 dòng
        it = wk["items"].setdefault((code, wage), {"code": code, "cay": 0.0, "wage": wage, "money": 0})
        it["cay"] = round(it["cay"] + cay, 1)
        it["money"] += money
        wk["cay"] = round(wk["cay"] + cay, 1)
        wk["money"] += money
        wk["allowance"] += a
        dy = wk["days"].setdefault(ymd or "", {"ymd": ymd or "", "cay": 0.0, "money": 0, "codes": []})
        dy["cay"] = round(dy["cay"] + cay, 1)
        dy["money"] += money
        if code and code not in dy["codes"]:
            dy["codes"].append(code)

        ph = phieus.setdefault(tid, {"thread_id": tid, "ymd": ymd, "codes": [], "cay": 0.0, "money": 0, "workers": 0, "_wk": set()})
        if code and code not in ph["codes"]:
            ph["codes"].append(code)
        ph["cay"] = round(ph["cay"] + cay, 1)
        ph["money"] += money
        ph["_wk"].add(worker)

    # Phụ cấp "mồ côi" (thợ có phụ cấp nhưng không có dòng SP trong phiếu) — vẫn cộng tiền
    for (tid, wname), amt in allow.items():
        amt = round(amt)
        if amt == 0 or (tid, wname) in allow_used or tid not in phieus:
            continue
        if only_cf is not None and str(wname or "").strip().casefold() not in only_cf:
            continue
        wk = workers.setdefault(wname, {"name": wname, "cay": 0.0, "money": 0, "allowance": 0, "items": {}, "days": {}})
        it = wk["items"].setdefault(("", 0.0), {"code": "", "cay": 0.0, "wage": 0.0, "money": 0})
        it["money"] += amt
        wk["money"] += amt
        wk["allowance"] += amt
        phieus[tid]["money"] += amt
        ph_ymd = phieus[tid]["ymd"] or ""
        dy = wk["days"].setdefault(ph_ymd, {"ymd": ph_ymd, "cay": 0.0, "money": 0, "codes": []})
        dy["money"] += amt

    phieu_list = []
    for tid in sorted(phieus, key=lambda t: (phieus[t]["ymd"] or "", t)):
        ph = phieus[tid]
        ph["workers"] = len(ph.pop("_wk"))
        phieu_list.append(ph)
    worker_list = sorted(workers.values(), key=lambda w: -w["money"])
    for wk in worker_list:
        wk["items"] = sorted(wk["items"].values(), key=lambda x: -x["money"])
        wk["days"] = sorted(wk["days"].values(), key=lambda d: d["ymd"])

    return {
        "workers": worker_list,
        "phieus": phieu_list,
        "totals": {
            "cay": round(sum(w["cay"] for w in worker_list), 1),
            "money": sum(w["money"] for w in worker_list),
            "allowance": sum(w["allowance"] for w in worker_list),
        },
        "missing_wage": sorted(c for c in missing if c),
    }
