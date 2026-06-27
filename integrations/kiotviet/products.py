from __future__ import annotations

from .core import _request


def search_products_kv(name: str, limit: int = 20) -> list[dict]:
    result = _request("GET", "/products", query_params={"search": name, "pageSize": limit})
    return result.get("data", [])


def get_product_by_id(product_id: int) -> dict | None:
    return _request("GET", f"/products/{product_id}")


def get_product_by_code(product_code: str) -> dict | None:
    result = _request("GET", "/products", query_params={"code": product_code, "pageSize": 1})
    data = result.get("data", [])
    return data[0] if data else None
