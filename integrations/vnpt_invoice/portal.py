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


def get_draft_view_html(fkey: str) -> str:
    """HTML bản thể hiện của hoá đơn NHÁP (getNewInvViewFkey) — để render PNG xem trong app."""
    if not fkey:
        raise VnptError("thiếu fkey khi xem hoá đơn")
    return _portal("getNewInvViewFkey", fkey)


def download_draft_pdf(fkey: str) -> bytes:
    """PDF bản thể hiện của hoá đơn NHÁP (chưa phát hành, Số = 00000000)."""
    if not fkey:
        raise VnptError("thiếu fkey khi tải PDF")
    b64 = _portal("downloadNewInvPDFFkey", fkey)
    try:
        pdf = base64.b64decode(b64)
    except Exception as e:
        raise VnptError("VNPT trả dữ liệu PDF không đọc được") from e
    if not pdf.startswith(b"%PDF"):
        raise VnptError("VNPT trả dữ liệu không phải PDF")
    return pdf
