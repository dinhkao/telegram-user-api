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
KIOTVIET_CLIENT_ID = os.getenv("KIOTVIET_CLIENT_ID", "")
KIOTVIET_CLIENT_SECRET = os.getenv("KIOTVIET_CLIENT_SECRET", "")
KIOTVIET_RETAILER = os.getenv("KIOTVIET_RETAILER", "")

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
        f"{KIOTVIET_BASE}/token",
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
