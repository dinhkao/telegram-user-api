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


def get_invoice_status(fkey: str) -> dict:
    """Tra trạng thái phát hành của hoá đơn theo fkey (GetInvoiceByFkey notax='0')."""
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
    return parse_invoice_status(raw)


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
