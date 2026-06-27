from __future__ import annotations

from .core import _request


def get_payment_methods() -> list[dict]:
    return _request("GET", "/paymentMethods").get("data", [])


def process_payment(payment_data: dict) -> dict:
    return _request("POST", "/payments", body=payment_data)


def get_payments_by_invoice(invoice_id: int) -> list[dict]:
    return _request("GET", "/payments", query_params={"invoiceId": invoice_id}).get("data", [])


def delete_payment_kv(payment_id: int) -> bool:
    _request("DELETE", f"/payments/{payment_id}")
    return True


def create_payment_kv(amount: int, method_code: str,
                      customer_id: int | None = None,
                      order_code: str | None = None) -> dict:
    body = {
        "amount": amount,
        "methodCode": method_code,
        "description": f"Payment for order {order_code or 'unknown'}",
    }
    if customer_id:
        body["customerId"] = customer_id
    if order_code:
        body["orderCode"] = order_code
    return _request("POST", "/payments", body=body)
