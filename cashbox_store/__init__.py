"""cashbox_store — hệ thống KÉT TIỀN "ai đang giữ tiền" (app.db + derive từ blob đơn).

Trạng thái két KHÔNG lưu bảng riêng mà DERIVE thuần từ blob đơn hàng (orders.json,
đơn từ SINCE) + bảng `cashbox_transfers` (chuyển tay giữa két). Mỗi đồng của một
đơn nằm ở đúng 1 két tại mọi thời điểm; mọi biến động là cặp cân bằng src→dst nên
tổng tiền bảo toàn theo cấu trúc (un-done task / xoá payment / sửa HĐ → recompute
tự đúng, không drift). Layer: identity (map tg-id↔web user, thuần) → domain
(máy trạng thái tiền mỗi đơn, thuần, unit-tested tests/test_cashbox_domain.py) →
schema/queries (bảng transfers) → service (ráp + cache). API:
server_app/cashbox_routes.py; UI webapp #/ket.
"""
from .identity import BOX_NAMES, box_display, build_canon  # noqa: F401
from .domain import EXTERNAL, SINCE, derive_order_movements  # noqa: F401
from .schema import ensure_table  # noqa: F401
from .queries import add_transfer, delete_transfer, get_transfer, list_transfers  # noqa: F401
from .service import cashbox_summary, cashbox_timeline, invalidate_cache  # noqa: F401
