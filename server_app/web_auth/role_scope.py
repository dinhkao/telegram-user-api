"""Giới hạn PHẠM VI API theo vai trò — logic THUẦN (không IO, unit-tested).

Hiện chỉ có một vai trò bị bó hẹp: **`chat_luong`** — user chỉ được xem và thao tác
trang CHẤT LƯỢNG MÂM KẸO (#/chat-luong), không thấy đơn hàng / kho / lương / khách.

⚠ Đây là hàng rào THẬT (chặn ở middleware, trước mọi handler). Ẩn menu ở webapp chỉ
là cho gọn mắt — người dùng gõ thẳng URL API vẫn phải bị 403. Nguyên tắc: **mặc định
TỪ CHỐI**, chỉ mở đúng những đường trang chất lượng cần. Thêm tính năng cho vai trò
này thì thêm đường vào đây, đừng nới lỏng bằng cách so khớp tiền tố lỏng lẻo.

Dùng bởi: server_app/web_auth/middleware.py
"""
from __future__ import annotations

# Vai trò chỉ-chất-lượng. Không nằm trong OFFICE_ROLES nên mọi gate văn phòng/admin
# sẵn có (xoá báo cáo, đổi cài đặt bảng…) tự động vẫn từ chối.
QUALITY_ONLY_ROLE = "chat_luong"

# Ảnh + bình luận + chấm điểm của trang chất lượng đi qua /api/media/{scope}/…
# CHỈ hai scope này được phép (area_* của trang vệ sinh KHÔNG).
_ALLOWED_MEDIA_SCOPES = frozenset({"quality_report", "quality_image"})

# Nhánh /api/<đây> được mở trọn cho vai trò này.
_ALLOWED_ROOTS = frozenset({
    "auth",       # /api/auth/login · /api/auth/me — không có thì không đăng nhập được
    "quality",    # /api/quality* — bảng + chi tiết thợ + tạo báo cáo hôm nay
})


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def allowed_for_quality_only(method: str, path: str) -> bool:
    """User vai trò `chat_luong` có được gọi (method, path) không.

    So khớp theo TỪNG ĐOẠN đường dẫn, không dùng startswith — nếu không thì
    '/api/quality-secret' hay '/api/media/quality_report_x/…' cũng lọt.
    """
    if (method or "").upper() == "OPTIONS":
        return True
    if not path.startswith("/api/"):
        return True                       # trang tĩnh / /ws — gate ở chỗ khác
    seg = _segments(path)                 # ['api', …]
    if len(seg) < 2:
        return False
    root = seg[1]
    if root in _ALLOWED_ROOTS:
        return True
    if root == "media" and len(seg) >= 3 and seg[2] in _ALLOWED_MEDIA_SCOPES:
        return True
    return False


def api_scope_denied(role: str | None, method: str, path: str) -> bool:
    """True nếu vai trò này KHÔNG được phép gọi đường dẫn đó (→ middleware trả 403).
    Vai trò khác (admin/van_phong/staff) không bị bó → luôn False."""
    if (role or "") != QUALITY_ONLY_ROLE:
        return False
    return not allowed_for_quality_only(method, path)
