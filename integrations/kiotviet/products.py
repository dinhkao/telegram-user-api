from __future__ import annotations
import os

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


def create_product_kv(code: str, name: str, *, unit: str = "", base_price: float = 0,
                      category_id: int | None = None) -> dict:
    """Tạo SP MỚI trên KiotViet (POST /products). Trả {id, code, full_name}.
    category_id lấy từ env KIOTVIET_DEFAULT_CATEGORY_ID nếu không truyền (KiotViet
    thường bắt buộc categoryId). Ném RuntimeError nếu KiotViet từ chối."""
    code = (code or "").strip().upper()
    name = (name or code).strip()
    if not code:
        raise RuntimeError("Thiếu mã SP")
    if category_id is None:
        env_cat = os.getenv("KIOTVIET_DEFAULT_CATEGORY_ID")
        category_id = int(env_cat) if env_cat and env_cat.strip().isdigit() else None
    body: dict = {"code": code, "name": name, "fullName": name}
    if unit:
        body["unit"] = unit
    if base_price:
        body["basePrice"] = base_price
    if category_id:
        body["categoryId"] = category_id
    res = _request("POST", "/products", body=body)
    return {
        "id": res.get("id"),
        "code": (res.get("code") or code).strip(),
        "full_name": res.get("fullName") or res.get("name") or name,
    }
