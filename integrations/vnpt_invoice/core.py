"""SOAP client VNPT-Invoice: dựng envelope, gọi PublishService.asmx, parse kết quả.

Đọc env VNPT_INV_* (.env, gitignored — không hardcode mật khẩu). Blocking
(urllib) như integrations/kiotviet/core.py — caller bọc asyncio.to_thread.
"""
from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

from lxml import etree

log = logging.getLogger("vnpt_invoice")

VNPT_INV_BASE = os.getenv("VNPT_INV_BASE_URL", "").rstrip("/")
# Tài khoản ADMIN trang điều hành (Account/ACpass trong SOAP)
VNPT_INV_ACCOUNT = os.getenv("VNPT_INV_ACCOUNT", "")
VNPT_INV_ACPASS = os.getenv("VNPT_INV_ACPASS", "")
# Tài khoản SERVICE (username/password trong SOAP)
VNPT_INV_SERVICE_USER = os.getenv("VNPT_INV_SERVICE_USER", "")
VNPT_INV_SERVICE_PASS = os.getenv("VNPT_INV_SERVICE_PASS", "")
# Mẫu số / ký hiệu — Duy chốt 2026-08-26: cố định 1/001 · C26TTP
VNPT_INV_PATTERN = os.getenv("VNPT_INV_PATTERN", "1/001")
VNPT_INV_SERIAL = os.getenv("VNPT_INV_SERIAL", "C26TTP")

_NS = "http://tempuri.org/"


class VnptError(RuntimeError):
    """Lỗi từ service VNPT — message đã dịch sẵn để hiện cho người dùng."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def configured() -> bool:
    return bool(VNPT_INV_BASE and VNPT_INV_SERVICE_USER and VNPT_INV_SERVICE_PASS)


def soap_call(operation: str, params: dict[str, object], timeout: int = 40,
              service: str = "PublishService.asmx") -> str:
    """Gọi 1 operation SOAP của VNPT (mặc định PublishService), trả string <XxxResult>.

    params giữ NGUYÊN THỨ TỰ khai báo (dict Python có thứ tự) — .asmx không
    khắt khe thứ tự nhưng cứ gửi đúng như trang mô tả cho chắc.
    """
    if not configured():
        raise VnptError("VNPT-Invoice chưa cấu hình (VNPT_INV_* trong .env)")
    inner = "".join(
        f"<{k}>{escape(str(v))}</{k}>" for k, v in params.items()
    )
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><{operation} xmlns="{_NS}">{inner}</{operation}></soap:Body>'
        "</soap:Envelope>"
    )
    req = urllib.request.Request(
        f"{VNPT_INV_BASE}/{service}",
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{_NS}{operation}"',
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        # KHÔNG log envelope (chứa mật khẩu) — chỉ log operation + body lỗi
        log.error("VNPT HTTP %d %s: %s", e.code, operation, text[:300])
        raise VnptError(f"VNPT trả HTTP {e.code} khi gọi {operation}") from e
    except Exception as e:
        log.error("VNPT request failed %s: %s", operation, e)
        raise VnptError(f"Không gọi được VNPT ({operation}): {e}") from e
    try:
        root = etree.fromstring(raw)
        node = root.find(f".//{{{_NS}}}{operation}Result")
    except Exception as e:
        raise VnptError(f"Không đọc được phản hồi VNPT ({operation})") from e
    if node is None or node.text is None:
        raise VnptError(f"VNPT trả phản hồi rỗng ({operation})")
    return node.text.strip()


# Bảng lỗi theo tài liệu tích hợp VNPT-Invoice (PublishService)
_ERR_MESSAGES = {
    "ERR:1": "Sai tài khoản service hoặc tài khoản không có quyền",
    "ERR:2": "Không tồn tại hoá đơn (sai fkey?)",
    "ERR:3": "Dữ liệu XML hoá đơn không đúng quy định",
    "ERR:5": "Lỗi không xác định phía VNPT",
    "ERR:6": "Dải số hoá đơn đã hết",
    "ERR:7": "Sai tài khoản admin (Account/ACpass)",
    "ERR:10": "Trùng fkey — hoá đơn với fkey này đã tồn tại",
    "ERR:13": "Hoá đơn đã phát hành/đã cấp số — không sửa/xoá nháp được",
    "ERR:20": "Mẫu số và ký hiệu không phù hợp",
}


def check_result(result: str, operation: str) -> str:
    """OK → trả nguyên chuỗi; ERR:x → raise VnptError với message tiếng Việt."""
    if result.upper().startswith("OK"):
        return result
    code = result.split(",")[0].split(";")[0].strip()
    msg = _ERR_MESSAGES.get(code.upper())
    if msg:
        raise VnptError(f"{msg} ({code})", code=code)
    raise VnptError(f"VNPT báo lỗi khi {operation}: {result[:200]}", code=code)
