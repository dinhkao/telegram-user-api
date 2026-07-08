from __future__ import annotations

from .core import _request, log


def get_customer_debt_kv(customer_id: int) -> dict:
    result = _request("GET", f"/customers/{customer_id}")
    return {
        "debt": result.get("debt", 0),
        "total_invoice": result.get("totalInvoice", 0),
        "total_payment": result.get("totalPayment", 0),
        "code": result.get("code", ""),
        "name": result.get("name", ""),
    }


def list_all_customers_kv(page_size: int = 100, max_pages: int = 200) -> list[dict]:
    """Kéo TOÀN BỘ khách từ KiotViet (phân trang pageSize/currentItem, max 100/trang;
    GET limit 5000 req/h — vài chục trang cho vài nghìn khách là thoải mái).
    Trả list dict thô (id, code, name, debt, …). Dùng: tools/sync_kv_debts.py."""
    out: list[dict] = []
    cur = 0
    for _ in range(max_pages):
        result = _request("GET", "/customers", query_params={
            "pageSize": page_size, "currentItem": cur,
            "orderBy": "id", "orderDirection": "Asc",
        })
        data = result.get("data", [])
        out.extend(data)
        cur += len(data)
        total = int(result.get("total") or 0)
        if not data or (total and cur >= total):
            break
    log.info("KiotViet: kéo %d khách", len(out))
    return out


def get_customer_by_code_kv(code: str) -> dict | None:
    result = _request("GET", "/customers", query_params={"code": code, "pageSize": 1})
    data = result.get("data", [])
    return data[0] if data else None


def search_customers_kv(name: str, limit: int = 20) -> list[dict]:
    result = _request("GET", "/customers", query_params={"search": name, "pageSize": limit})
    return result.get("data", [])


def create_customer_kv(customer_data: dict, branch_id: int = 1133) -> dict:
    payload = {
        "branchId": branch_id,
        "name": customer_data.get("name", ""),
        "gender": customer_data.get("gender", "Unknown"),
        "type": customer_data.get("type", 0),
    }
    if customer_data.get("contactNumber"):
        payload["contactNumber"] = customer_data["contactNumber"]
    if customer_data.get("address"):
        payload["address"] = customer_data["address"]
    log.info("Creating KiotViet customer: %s", payload.get("name"))
    result = _request("POST", "/customers", body=payload)
    created = result.get("data")
    if not created or not created.get("id"):
        raise RuntimeError(f"KiotViet createCustomer failed: {result}")
    log.info("KiotViet customer created: id=%s name=%s", created.get("id"), created.get("name"))
    return created
