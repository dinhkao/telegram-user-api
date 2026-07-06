from __future__ import annotations

from .core import _request


def search_products_kv(name: str, limit: int = 20) -> list[dict]:
    """Tìm sản phẩm KiotViet theo TÊN (để liên kết từng mã local). Trả bản gọn
    [{id, code, full_name}] cho UI chọn. Lưu ý: KiotViet /products chỉ lọc bằng
    param `name` (param `code`/`search` bị bỏ qua → trả cả danh mục)."""
    result = _request("GET", "/products", query_params={"name": name, "pageSize": limit})
    out = []
    for p in result.get("data", []):
        out.append({"id": p.get("id"), "code": (p.get("code") or "").strip(),
                    "full_name": p.get("fullName") or p.get("name") or ""})
    return out


def get_product_by_id(product_id: int) -> dict | None:
    return _request("GET", f"/products/{product_id}")


def get_product_by_code(product_code: str) -> dict | None:
    result = _request("GET", "/products", query_params={"code": product_code, "pageSize": 1})
    data = result.get("data", [])
    return data[0] if data else None
