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
