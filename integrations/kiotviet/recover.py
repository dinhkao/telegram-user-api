"""So khớp HĐ KiotViet "mồ côi" — logic THUẦN, không IO.

Khi POST /invoices bị timeout, KiotViet vẫn có thể đã tạo HĐ (đã xảy ra
2026-08-09: HD085869 tạo lúc 16:16:02 nhưng response không về trong 30s → app
báo lỗi, đơn không có kiotvietInvoiceID → bấm lại là tạo HĐ TRÙNG). Module này
nhận danh sách HĐ gần đây của khách + các dòng ta VỪA GỬI, chọn ra HĐ đúng là
của lần gửi đó. Dùng bởi api_helpers/invoice_recover.py (nơi có IO + DB).
"""
from __future__ import annotations

from datetime import datetime


def parse_kv_time(s) -> datetime | None:
    """'2026-08-09T16:16:02.3830000' → datetime (giờ VN, naive). Lỗi → None."""
    if not s:
        return None
    txt = str(s).strip().replace("Z", "")
    # KiotViet trả 7 chữ số phần giây — fromisoformat chỉ chịu tối đa 6.
    if "." in txt:
        head, frac = txt.split(".", 1)
        txt = f"{head}.{frac[:6]}"
    try:
        return datetime.fromisoformat(txt)
    except ValueError:
        return None


def _line_key(d: dict) -> tuple:
    """Dòng HĐ → khoá so khớp. Ưu tiên productId (danh tính KiotViet bất biến),
    không có thì dùng productCode viết hoa."""
    pid = d.get("productId")
    code = str(d.get("productCode") or "").strip().upper()
    ident = int(pid) if pid else code
    return (ident, float(d.get("quantity") or 0), float(d.get("price") or 0))


def details_match(sent: list[dict], got: list[dict]) -> bool:
    """Các dòng ta gửi và các dòng HĐ trả về có TRÙNG KHỚP hoàn toàn không.

    Ta gửi productId HOẶC productCode; HĐ trả về có cả hai → so theo đúng thứ
    ta đã gửi từng dòng. Số dòng phải bằng nhau (multiset, không quan tâm thứ tự).
    """
    if len(sent) != len(got):
        return False
    pool = list(got)
    for s in sent:
        want = _line_key(s)
        by_id = isinstance(want[0], int)
        for i, g in enumerate(pool):
            ident = int(g.get("productId")) if by_id and g.get("productId") else \
                str(g.get("productCode") or "").strip().upper()
            if (ident, float(g.get("quantity") or 0), float(g.get("price") or 0)) == want:
                pool.pop(i)
                break
        else:
            return False
    return True


def pick_orphan(invoices: list[dict], *, sent_details: list[dict],
                since: datetime, used_ids: set[int] | None = None) -> dict | None:
    """Chọn HĐ mồ côi trong danh sách HĐ của khách.

    Điều kiện (phải đủ CẢ BA, thà bỏ sót còn hơn nhận nhầm HĐ của đơn khác):
      1. tạo SAU mốc `since` (ngay trước lúc ta gửi POST),
      2. các dòng khớp hệt `sent_details`,
      3. id chưa gắn vào đơn nào (`used_ids`).
    Nhiều ứng viên → lấy cái tạo SỚM NHẤT sau mốc (chính là lần gửi của ta).
    """
    used = used_ids or set()
    hits = []
    for inv in invoices or []:
        try:
            inv_id = int(inv.get("id"))
        except (TypeError, ValueError):
            continue
        if inv_id in used:
            continue
        at = parse_kv_time(inv.get("createdDate") or inv.get("purchaseDate"))
        if at is None or at < since:
            continue
        if not details_match(sent_details, inv.get("invoiceDetails") or []):
            continue
        hits.append((at, inv))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0])
    return hits[0][1]
