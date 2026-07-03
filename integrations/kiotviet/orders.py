from __future__ import annotations

from .core import _request, log


def create_order_with_payment(customer_id: int, method: str, total_payment: int | str,
                              account_id: int | None = None, branch_id: int = 1133,
                              sold_by_id: int = 186250, order_details: list[dict] | None = None,
                              make_invoice: bool = False) -> dict:
    if order_details is None:
        order_details = [{"productCode": "test", "quantity": 1, "price": 1}]
    payload = {
        "branchId": branch_id,
        "soldById": sold_by_id,
        "method": method,
        "totalPayment": int(total_payment),
        "makeInvoice": make_invoice,
        "orderDetails": order_details,
        "customer": {"id": customer_id},
    }
    if account_id:
        payload["accountId"] = account_id
    log.info("Creating KiotViet order+pymt: cust=%d method=%s amt=%s acct=%s",
             customer_id, method, total_payment, account_id)
    return _request("POST", "/orders", body=payload)


def delete_order_kv(order_id: int, void_payment: bool = True) -> bool:
    """Xoá 1 phiếu đặt hàng (DH) trên KiotViet → payment nhúng trong nó mất theo.
    Thanh toán ở app tạo bằng workaround POST /orders (create_order_with_payment)
    nên KHÔNG có payment độc lập để xoá — phải xoá cả phiếu đặt hàng. Theo mẫu
    delete_invoice_kv: DELETE ở endpoint tập hợp + body chứa id."""
    # isVoidPayment=true để huỷ luôn phiếu thu (TTDH) — nếu không, xoá đơn nhưng
    # thanh toán vẫn còn trên KiotViet. Gửi cả body (theo mẫu delete_invoice_kv) lẫn
    # query cho chắc (KiotViet có thể đọc 1 trong 2).
    _request("DELETE", f"/orders/{order_id}",
             body={"isVoidPayment": void_payment},
             query_params={"isVoidPayment": str(void_payment).lower()})
    log.info("KiotViet order deleted: id=%d void_payment=%s", order_id, void_payment)
    return True
