"""Khung CHI TIẾT + LINK cho lịch sử thao tác (dùng chung 3 mặt hiển thị).

Một dòng lịch sử ngoài (action, detail) giờ có thêm ``parts``: danh sách đoạn
``{t}`` (chữ thường) / ``{t, href}`` (link tới trang thực thể được nhắc tới —
thùng/SP/khách/đơn/phiếu...). Client (History.tsx, ActivityLog.tsx) render parts;
``detail`` = text ghép lại (fallback + search). Nối: server_app/order_history,
entity_history, activity, event_format; webapp/src/detail/History.tsx.
"""
from __future__ import annotations


def part(t, href: str | None = None) -> dict:
    p = {"t": str(t)}
    if href:
        p["href"] = href
    return p


def parts_text(parts: list[dict]) -> str:
    """Ghép parts → text thuần cho field detail (fallback/search)."""
    return "".join(p.get("t", "") for p in (parts or []))


def money(v) -> str:
    try:
        return f"{int(round(float(v))):,}đ".replace(",", ".")
    except (TypeError, ValueError):
        return str(v or "")


def qty(v) -> str:
    """Số lượng gọn: 5.0 → '5', 5.5 → '5,5'."""
    try:
        return f"{float(v):g}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v or "")


def boxnum(code) -> str:
    """Số gọi ngắn của thùng: 'K2L-347' → '347'."""
    s = str(code or "")
    return s.split("-")[-1] or s


# scope → hàm dựng href trang chi tiết (khớp route webapp/src/main.tsx)
_HREF = {
    "order": lambda e: f"#/order/{e}",
    "production": lambda e: f"#/san_xuat/{e}",
    "box": lambda e: f"#/thung/{e}",
    "place": lambda e: f"#/vi-tri/{e}",
    "task": lambda e: f"#/viec/{e}",
    "customer": lambda e: f"#/khach/{e}",
    "return": lambda e: f"#/tra-hang/{e}",
    "disposal": lambda e: f"#/xuat-huy/{e}",
    "purchase": lambda e: f"#/nhap-hang/{e}",
    "supplier": lambda e: f"#/ncc/{e}",
    "price": lambda e: f"#/bang-gia/{e}",
    "quy": lambda e: "#/quy",
    "report_slip": lambda e: f"#/bao-cao/{e}",
    "stocktake": lambda e: f"#/kiem-kho/{e}",
    "area": lambda e: f"#/khu-vuc/{e}",
}


def href_for(scope: str, eid) -> str:
    fn = _HREF.get(scope)
    return fn(eid) if (fn and eid is not None) else ""


def product_href(code) -> str:
    return f"#/kho/{code}" if code else ""


class Resolver:
    """Tra tên/thông tin thực thể để dòng lịch sử đọc được (best-effort, cache
    trong 1 request). Mọi lookup nuốt lỗi — lịch sử không được chết vì thiếu bảng."""

    def __init__(self, conn):
        self.conn = conn
        self._c: dict = {}

    def _one(self, key, sql, args):
        if key in self._c:
            return self._c[key]
        val = None
        try:
            row = self.conn.execute(sql, args).fetchone()
            val = row[0] if row else None
        except Exception:
            val = None
        self._c[key] = val
        return val

    def customer_name(self, key) -> str | None:
        if key is None or str(key) == "":
            return None
        return self._one(("kh", str(key)),
                         "SELECT COALESCE(json_extract(json,'$.name'), json_extract(json,'$.ten_khach_hang')) "
                         "FROM customers WHERE firebase_key = ?", (str(key),))

    def supplier_name(self, sid) -> str | None:
        return self._one(("ncc", sid), "SELECT name FROM suppliers WHERE id = ?", (sid,)) if sid else None

    def place_name(self, pid) -> str | None:
        return self._one(("pl", pid), "SELECT name FROM inventory_places WHERE id = ?", (pid,)) if pid else None

    def unit_name(self, uid) -> str | None:
        return self._one(("un", uid), "SELECT name FROM inventory_units WHERE id = ?", (uid,)) if uid else None

    def product_code_by_id(self, pid) -> str | None:
        return self._one(("spid", pid), "SELECT code FROM products WHERE id = ?", (pid,)) if pid else None

    def product_name(self, code) -> str | None:
        if not code:
            return None
        return self._one(("sp", str(code)), "SELECT name FROM products WHERE code = ?", (str(code),))

    def box_brief(self, box_id) -> dict | None:
        """{num, product_code, unit} của 1 thùng — cho event cũ thiếu field."""
        if not box_id:
            return None
        key = ("box", box_id)
        if key in self._c:
            return self._c[key]
        val = None
        try:
            row = self.conn.execute(
                "SELECT b.box_code, b.product_code, COALESCE(p.unit,'') FROM inventory_boxes b "
                "LEFT JOIN products p ON p.code = b.product_code WHERE b.id = ?", (box_id,)).fetchone()
            if row:
                val = {"num": boxnum(row[0]), "product_code": row[1], "unit": row[2] or "cây"}
        except Exception:
            val = None
        self._c[key] = val
        return val

    def order_text(self, tid) -> str | None:
        if not tid:
            return None
        t = self._one(("ord", tid),
                      "SELECT COALESCE(json_extract(json,'$.text'), json_extract(json,'$.text_raw')) "
                      "FROM orders WHERE thread_id = ?", (tid,))
        return " ".join(str(t).split())[:40] if t else None


def customer_part(key, resolver: Resolver) -> dict:
    """1 part tên khách (link) — fallback key thô nếu chưa tra được."""
    name = resolver.customer_name(key) if resolver else None
    return part(name or f"khách #{key}", href_for("customer", key))


def box_part(box_id, box_code, resolver: Resolver) -> dict:
    num = boxnum(box_code)
    if not num and resolver:
        b = resolver.box_brief(box_id)
        num = (b or {}).get("num", "")
    return part(f"thùng {num or ('#' + str(box_id))}", href_for("box", box_id) if box_id else None)
