from __future__ import annotations

from .core import _request, log


def list_all_products_kv(page_size: int = 100, max_pages: int = 200) -> list[dict]:
    """Kéo TOÀN BỘ danh mục sản phẩm KiotViet (phân trang) → [{id, code, full_name}].
    Dùng để đồng bộ vào product_store (liên kết code↔KiotViet). Dừng khi hết data
    hoặc chạm max_pages (chặn vòng lặp)."""
    out: list[dict] = []
    current = 0
    for _ in range(max_pages):
        res = _request("GET", "/products", query_params={"pageSize": page_size, "currentItem": current})
        data = res.get("data") or []
        if not data:
            break
        for p in data:
            code = (p.get("code") or "").strip()
            if not code:
                continue
            out.append({"id": p.get("id"), "code": code,
                        "full_name": p.get("fullName") or p.get("name") or ""})
        current += len(data)
        total = res.get("total")
        if total is not None and current >= int(total):
            break
    log.info("KiotViet products fetched: %d", len(out))
    return out


def search_products_kv(name: str, limit: int = 20) -> list[dict]:
    result = _request("GET", "/products", query_params={"search": name, "pageSize": limit})
    return result.get("data", [])


def get_product_by_id(product_id: int) -> dict | None:
    return _request("GET", f"/products/{product_id}")


def get_product_by_code(product_code: str) -> dict | None:
    result = _request("GET", "/products", query_params={"code": product_code, "pageSize": 1})
    data = result.get("data", [])
    return data[0] if data else None
