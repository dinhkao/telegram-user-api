"""Tích hợp VNPT-Invoice (HĐĐT TT78) — CHỈ hoá đơn NHÁP (chưa phát hành).

Nói chuyện với PublishService.asmx của VNPT bằng SOAP tự dựng (lxml + urllib,
blocking — caller phải bọc asyncio.to_thread). Chỉ dùng các operation nháp:
ImportInvByPattern / updateInvoice / deleteInvoiceByFkey / getStatusInv.
TUYỆT ĐỐI không gọi nhóm Publish* (phát hành) từ package này.
"""
from .core import VnptError, soap_call, VNPT_INV_PATTERN, VNPT_INV_SERIAL
from .amount_words import amount_to_words
from .xml_build import compute_totals, build_invoice_xml, VAT_RATES
from .invoices import (
    import_draft,
    delete_draft,
    get_draft_status,
)
from .portal import download_draft_pdf, get_draft_view_html

__all__ = [
    "VnptError",
    "soap_call",
    "VNPT_INV_PATTERN",
    "VNPT_INV_SERIAL",
    "amount_to_words",
    "compute_totals",
    "build_invoice_xml",
    "VAT_RATES",
    "import_draft",
    "delete_draft",
    "get_draft_status",
    "download_draft_pdf",
    "get_draft_view_html",
]
