"""Xem/tải hoá đơn nháp qua PortalService.asmx (dùng tài khoản SERVICE).

Blocking — caller bọc asyncio.to_thread. ⚠ Với nháp CHƯA phát hành chỉ nhóm
`*New*` hoạt động (thực nghiệm 2026-08-26): downloadNewInvPDFFkey trả base64
PDF, getNewInvViewFkey trả HTML; còn downloadInvPDFFkey/getInvViewFkey trả
ERR:6 (chỉ cho HĐ đã phát hành).
"""
from __future__ import annotations

import base64

from . import core
from .core import VnptError, soap_call

_PORTAL_ERRS = {
    "ERR:1": "Sai tài khoản khi tải hoá đơn từ VNPT",
    "ERR:6": "Không tìm thấy hoá đơn trên VNPT (sai fkey hoặc đã bị xoá)",
}


def _portal(operation: str, fkey: str) -> str:
    result = soap_call(
        operation,
        {"fkey": fkey,
         "userName": core.VNPT_INV_SERVICE_USER,
         "userPass": core.VNPT_INV_SERVICE_PASS},
        service="PortalService.asmx",
    )
    if result.upper().startswith("ERR"):
        code = result.strip()
        raise VnptError(_PORTAL_ERRS.get(code, f"VNPT báo lỗi ({code})"), code=code)
    return result


def _portal_try(ops: tuple[str, ...], fkey: str) -> str:
    """Thử lần lượt các operation (nhóm *New* cho nháp, nhóm thường cho HĐ ĐÃ
    PHÁT HÀNH) — cái nào được thì lấy."""
    last: VnptError | None = None
    for op in ops:
        try:
            return _portal(op, fkey)
        except VnptError as e:
            last = e
    raise last  # type: ignore[misc]


def get_draft_view_html(fkey: str) -> str:
    """HTML bản thể hiện của hoá đơn (nháp HOẶC đã phát hành) — để render PNG xem
    trong app. Thứ tự op (thực nghiệm 2026-08-26): *New* = nháp; *NoPay = đã phát
    hành nhưng CHƯA gạch thanh toán; bản thường = đã phát hành + đã thanh toán
    (gọi sớm hơn trả ERR:11)."""
    if not fkey:
        raise VnptError("thiếu fkey khi xem hoá đơn")
    return _portal_try(("getNewInvViewFkey", "getInvViewFkeyNoPay", "getInvViewFkey"), fkey)


def parse_links(b64: str) -> dict:
    """Payload base64 của GetLinkInvViewFkey → {view, xml, pdf} (URL công khai có
    token). Thuần, unit-tested."""
    import re
    try:
        text = base64.b64decode(b64).decode("utf-8", "replace")
    except Exception as e:
        raise VnptError("Không đọc được link hoá đơn từ VNPT") from e
    def g(tag: str) -> str:
        m = re.search(rf"<Link{tag}>([^<]+)</Link{tag}>", text)
        return m.group(1) if m else ""
    return {"view": g("View"), "xml": g("XML"), "pdf": g("PDF")}


def get_invoice_links(fkey: str) -> dict:
    """Link công khai (view/xml/pdf) của hoá đơn ĐÃ PHÁT HÀNH. Nháp chưa phát
    hành → ERR:6 (VnptError) — chính là TÍN HIỆU trạng thái phát hành."""
    if not fkey:
        raise VnptError("thiếu fkey")
    return parse_links(_portal("GetLinkInvViewFkey", fkey))


def download_draft_pdf(fkey: str) -> bytes:
    """PDF bản thể hiện của hoá đơn (nháp: Số = 00000000; đã phát hành: op thường)."""
    if not fkey:
        raise VnptError("thiếu fkey khi tải PDF")
    b64 = _portal_try(("downloadNewInvPDFFkey", "downloadInvPDFFkeyNoPay", "downloadInvPDFFkey"), fkey)
    try:
        pdf = base64.b64decode(b64)
    except Exception as e:
        raise VnptError("VNPT trả dữ liệu PDF không đọc được") from e
    if not pdf.startswith(b"%PDF"):
        raise VnptError("VNPT trả dữ liệu không phải PDF")
    return pdf
