"""Các thao tác hoá đơn NHÁP VNPT: tạo / xoá / tra trạng thái.

Blocking — caller bọc asyncio.to_thread. KHÔNG có hàm phát hành nào ở đây.
⚠ updateInvoice bị VNPT KHOÁ trên TT78 (trả "deprecated function", thực nghiệm
2026-08-26) → SỬA nháp = tạo nháp mới (fkey mới) rồi xoá nháp cũ; orchestration
nằm ở server_app/vnpt_invoice_routes.py.
"""
from __future__ import annotations

import logging

from . import core
from .core import VnptError, check_result, soap_call

log = logging.getLogger("vnpt_invoice")


def _service_auth() -> dict:
    return {
        "username": core.VNPT_INV_SERVICE_USER,
        "password": core.VNPT_INV_SERVICE_PASS,
    }


def import_draft(xml_inv_data: str) -> str:
    """Tạo hoá đơn NHÁP (ImportInvByPattern, convert=0 — KHÔNG phát hành)."""
    result = soap_call(
        "ImportInvByPattern",
        {
            "Account": core.VNPT_INV_ACCOUNT,
            "ACpass": core.VNPT_INV_ACPASS,
            "xmlInvData": xml_inv_data,
            **_service_auth(),
            "pattern": core.VNPT_INV_PATTERN,
            "serial": core.VNPT_INV_SERIAL,
            "convert": 0,
        },
    )
    return check_result(result, "tạo hoá đơn nháp")


def delete_draft(fkey: str, *, missing_ok: bool = False) -> str:
    """Xoá hoá đơn NHÁP theo fkey. missing_ok=True: fkey không còn trên VNPT
    (ERR:5 — vd đã bị xoá tay trên portal) coi như xong, không raise."""
    if not fkey:
        raise VnptError("thiếu fkey khi xoá hoá đơn nháp")
    result = soap_call(
        "deleteInvoiceByFkey",
        {
            "lstFkey": fkey,
            **_service_auth(),
            "Account": core.VNPT_INV_ACCOUNT,
            "ACpass": core.VNPT_INV_ACPASS,
        },
    )
    try:
        return check_result(result, "xoá hoá đơn nháp")
    except VnptError as e:
        if missing_ok and e.code == "ERR:5":
            log.warning("delete_draft %s: không còn trên VNPT (%s) — bỏ qua", fkey, e.code)
            return "OK:missing"
        raise


def parse_invoice_status(raw: str) -> dict:
    """Parse phản hồi GetInvoiceByFkey notax='0' (thực nghiệm 2026-08-26):
    <Results>…<No>0</No>…</Results> = còn NHÁP · <No> > 0 = ĐÃ PHÁT HÀNH (kèm
    MTC/QRCode của CQT) · <RV>…<MSGCODE>ERR:404</MSGCODE> = không còn trên VNPT.
    Thuần, unit-tested. Trả {exists, published, no, mtc}."""
    from lxml import etree
    try:
        root = etree.fromstring(raw.encode("utf-8"))
    except Exception as e:
        raise VnptError("Không đọc được trạng thái hoá đơn từ VNPT") from e
    msg = (root.findtext(".//MSGCODE") or "").strip().upper()
    if msg:
        if msg == "ERR:404":
            return {"exists": False, "published": False, "no": 0, "mtc": ""}
        raise VnptError(f"VNPT báo lỗi khi tra trạng thái ({msg})", code=msg)
    try:
        no = int(root.findtext(".//No") or 0)
    except ValueError:
        no = 0
    return {"exists": True, "published": no > 0, "no": no,
            "mtc": (root.findtext(".//MTC") or "").strip()}


def parse_published_xml(xml_text: str) -> tuple[int, str]:
    """XML hoá đơn TT78 (LinkXML công khai) → (số hoá đơn SHDon, mã CQT MCCQT).
    Thuần, unit-tested."""
    import re
    m = re.search(r"<SHDon>\s*(\d+)\s*</SHDon>", xml_text)
    no = int(m.group(1)) if m else 0
    m2 = re.search(r"<MCCQT[^>]*>\s*([^<]+?)\s*</MCCQT>", xml_text)
    return no, (m2.group(1) if m2 else "")


def get_invoice_status(fkey: str) -> dict:
    """Tra trạng thái phát hành của hoá đơn theo fkey.

    2 bước (thực nghiệm 2026-08-26): GetInvoiceByFkey notax='0' chỉ thấy hoá đơn
    SỐ 0 (= nháp) — hoá đơn ĐÃ PHÁT HÀNH mang số thật nên trả ERR:404 y như đã
    xoá. Gặp 404 phải dò tiếp GetLinkInvViewFkey (chỉ OK khi ĐÃ phát hành; nháp/
    đã xoá → ERR:6) rồi đọc số hoá đơn từ LinkXML (<SHDon>)."""
    if not fkey:
        raise VnptError("thiếu fkey khi tra trạng thái")
    raw = soap_call(
        "GetInvoiceByFkey",
        {
            **_service_auth(),
            "comtaxcode": core.VNPT_INV_TAXCODE,
            "pattern": core.VNPT_INV_PATTERN,
            "serial": core.VNPT_INV_SERIAL,
            "notax": "0",
            "fkey": fkey,
        },
    )
    st = parse_invoice_status(raw)
    if st["exists"]:
        return st
    # notax=0 báo 404: hoặc ĐÃ PHÁT HÀNH (mang số thật) hoặc mất thật — dò link
    from .portal import get_invoice_links
    try:
        links = get_invoice_links(fkey)
    except VnptError:
        return {"exists": False, "published": False, "no": 0, "mtc": ""}
    no, mtc = 0, ""
    if links.get("xml"):
        try:
            import urllib.request
            with urllib.request.urlopen(links["xml"], timeout=20) as resp:
                no, mtc = parse_published_xml(resp.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001 — thiếu số vẫn hơn báo sai trạng thái
            log.warning("get_invoice_status %s: đọc LinkXML lỗi: %s", fkey, e)
    return {"exists": True, "published": True, "no": no, "mtc": mtc}


def get_draft_status(fkey: str) -> str:
    """Tra trạng thái hoá đơn theo fkey (getStatusInv) — trả chuỗi thô VNPT.
    (Hoá đơn CHƯA phát hành trả '<Invoices></Invoices>' rỗng — thực nghiệm.)"""
    xml_fkey = f"<Fkeys><Fkey>{fkey}</Fkey></Fkeys>"
    return soap_call(
        "getStatusInv",
        {
            "Account": core.VNPT_INV_ACCOUNT,
            "ACpass": core.VNPT_INV_ACPASS,
            **_service_auth(),
            "xmlFkeyInv": xml_fkey,
            "pattern": core.VNPT_INV_PATTERN,
        },
    )
