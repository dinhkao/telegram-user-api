"""kiotviet.py — KiotViet REST API client with OAuth token refresh.

Uses stdlib only (urllib) — no aiohttp dependency needed for
Telethon's sync-on-thread-pool model.
"""
from __future__ import annotations
import json
import logging
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

log = logging.getLogger("kiotviet")

KIOTVIET_BASE = os.getenv("KIOTVIET_BASE_URL", "https://public.kiotapi.com")
KIOTVIET_TOKEN_URL = os.getenv("KIOTVIET_TOKEN_URL", "https://id.kiotviet.vn/connect/token")
KIOTVIET_CLIENT_ID = os.getenv("KIOTVIET_CLIENT_ID", "1c88abb0-61d0-48a9-b179-e9ec94bade9f")
KIOTVIET_CLIENT_SECRET = os.getenv("KIOTVIET_CLIENT_SECRET", "65FE124DBB02D060F5D09EB5B5B34485173A2782")
KIOTVIET_RETAILER = os.getenv("KIOTVIET_RETAILER", "letrangphat")

_token: str | None = None
_token_expires: float = 0.0


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    query_params: dict | None = None,
    retry: bool = True,
    timeout: int = 20,
) -> dict[str, Any]:
    global _token, _token_expires

    if not KIOTVIET_CLIENT_ID:
        raise RuntimeError("KIOTVIET_CLIENT_ID not configured")

    # Refresh token if needed
    if not _token or time.time() > _token_expires - 60:
        _refresh_token()

    url = f"{KIOTVIET_BASE}{path}"
    if query_params:
        url += "?" + urllib.parse.urlencode(query_params)

    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    headers = {
        "Authorization": f"Bearer {_token}",
        "Retailer": KIOTVIET_RETAILER,
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            log.warning("KiotViet token expired, refreshing...")
            _token = None
            return _request(method, path, body, query_params, retry=False, timeout=timeout)
        body_text = e.read().decode(errors="replace")
        log.error("KiotViet HTTP %d %s: %s", e.code, path, body_text[:300])
        raise RuntimeError(f"KiotViet API error {e.code}: {body_text[:200]}") from e
    except Exception as e:
        log.error("KiotViet request failed %s: %s", path, e)
        raise


def _refresh_token():
    global _token, _token_expires
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": KIOTVIET_CLIENT_ID,
        "client_secret": KIOTVIET_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        KIOTVIET_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    _token = result["access_token"]
    _token_expires = time.time() + result.get("expires_in", 3600)
    log.info("KiotViet token refreshed, expires in %ds", result.get("expires_in", 3600))


# ── Public API ──────────────────────────────────────────────────────

def search_products_kv(name: str, limit: int = 20) -> list[dict]:
    """Search KiotViet products by name/code."""
    result = _request("GET", "/products", query_params={
        "search": name,
        "pageSize": limit,
    })
    return result.get("data", [])


def get_product_by_id(product_id: int) -> dict | None:
    """Get single product by ID."""
    result = _request("GET", f"/products/{product_id}")
    return result


def get_product_by_code(product_code: str) -> dict | None:
    """Get product by code."""
    result = _request("GET", "/products", query_params={
        "code": product_code,
        "pageSize": 1,
    })
    data = result.get("data", [])
    return data[0] if data else None


def create_invoice(invoice_data: dict) -> dict:
    """Create an invoice in KiotViet."""
    return _request("POST", "/invoices", body=invoice_data)


def get_invoices_by_order(order_code: str | int, limit: int = 10) -> list[dict]:
    """Fetch invoices for a given order code."""
    result = _request("GET", "/invoices", query_params={
        "orderCode": str(order_code),
        "pageSize": limit,
    })
    return result.get("data", [])


def get_invoice_detail(invoice_id: int) -> dict | None:
    """Get full invoice detail including line items."""
    result = _request("GET", f"/invoices/{invoice_id}")
    return result


def get_payment_methods() -> list[dict]:
    """List payment methods."""
    result = _request("GET", "/paymentMethods")
    return result.get("data", [])


def process_payment(payment_data: dict) -> dict:
    """Process a payment."""
    return _request("POST", "/payments", body=payment_data)


def get_payments_by_invoice(invoice_id: int) -> list[dict]:
    """Get payments for an invoice."""
    result = _request("GET", f"/payments?invoiceId={invoice_id}")
    return result.get("data", [])


def delete_payment_kv(payment_id: int) -> bool:
    """Delete a payment from KiotViet."""
    _request("DELETE", f"/payments/{payment_id}")
    return True
def create_payment_kv(amount: int, method_code: str, customer_id: int | None = None, order_code: str | None = None) -> dict:
    """Create a payment in KiotViet. Returns the payment response."""
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


def get_customer_debt_kv(customer_id: int) -> dict:
    """Get customer debt from KiotViet."""
    result = _request("GET", f"/customers/{customer_id}")
    return {
        "debt": result.get("debt", 0),
        "total_invoice": result.get("totalInvoice", 0),
        "total_payment": result.get("totalPayment", 0),
        "code": result.get("code", ""),
        "name": result.get("name", ""),
    }


def get_customer_by_code_kv(code: str) -> dict | None:
    """Find customer by code."""
    result = _request("GET", "/customers", query_params={"code": code, "pageSize": 1})
    data = result.get("data", [])
    return data[0] if data else None


def search_customers_kv(name: str, limit: int = 20) -> list[dict]:
    """Search KiotViet customers by name."""
    result = _request("GET", "/customers", query_params={"search": name, "pageSize": limit})
    return result.get("data", [])


def create_order_with_payment(
    customer_id: int,
    method: str,
    total_payment: int | str,
    account_id: int | None = None,
    branch_id: int = 1133,
    sold_by_id: int = 186250,
    order_details: list[dict] | None = None,
    make_invoice: bool = False,
) -> dict:
    """Create a KiotViet order with embedded payment.
    
    Mirrors Node.js KiotVietService.createOrderWithPayment().
    Calls POST /orders with payment info embedded.
    
    Args:
        customer_id: KiotViet customer ID (kh_id)
        method: 'Cash' or 'Transfer'
        total_payment: Payment amount (int or string)
        account_id: For 'Transfer', the bank account ID (default: 1)
        branch_id: KiotViet branch ID
        sold_by_id: KiotViet seller ID
        order_details: Line items (default: 1 test item)
        make_invoice: Whether to auto-create invoice
    """
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


def create_kiotviet_invoice(
    customer_id: int,
    invoice_items: list[dict],
    discount: int = 0,
    pvc: int = 0,
    vat: int = 0,
    branch_id: int = 1133,
    sold_by_id: int = 186250,
) -> dict:
    """Create a KiotViet invoice from invoice items.
    
    Mirrors Node.js KiotVietService.createInvoice().
    
    Args:
        customer_id: KiotViet customer ID (kh_id)
        invoice_items: List of {sp, sl, price, note}
        discount: Discount amount
        pvc: Shipping/service charge
        vat: VAT amount
    """
    invoice_details = []
    for item in invoice_items:
        product_code = item.get("sp") or item.get("productCode", "test")
        quantity = int(item.get("sl", item.get("quantity", 1)))
        price = int(item.get("price", 0))
        note = str(item.get("note", "")) if item.get("note") else ""
        invoice_details.append({
            "productCode": product_code,
            "quantity": quantity,
            "price": price,
            "note": note,
        })

    payload = {
        "branchId": branch_id,
        "soldById": sold_by_id,
        "invoiceDetails": invoice_details,
        "customer": {"id": customer_id},
        "usingCod": True,
        "deliveryDetail": {"status": 1},
    }

    if discount:
        payload["discount"] = discount

    surcharges = []
    if pvc:
        surcharges.append({
            "id": 1000000298,
            "code": "THK000003",
            "price": pvc,
        })
    if vat:
        surcharges.append({
            "id": 1865,
            "code": "THK000001",
            "price": vat,
        })
    if surcharges:
        payload["surchages"] = surcharges

    log.info("Creating KiotViet invoice: cust=%d items=%d disc=%s pvc=%s vat=%s",
             customer_id, len(invoice_details), discount, pvc, vat)

    return _request("POST", "/invoices", body=payload)
