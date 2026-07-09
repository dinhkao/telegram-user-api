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


def list_categories_kv(limit: int = 100) -> list[dict]:
    """Danh sách nhóm hàng KiotViet (để chọn khi tạo SP). Trả [{id, name}]."""
    result = _request("GET", "/categories", query_params={"pageSize": limit})
    out = []
    for c in result.get("data", []):
        out.append({"id": c.get("categoryId") or c.get("id"),
                    "name": c.get("categoryName") or c.get("name") or ""})
    return out


def update_product_code_kv(kv_id: int, new_code: str) -> dict:
    """Đổi CODE của 1 SP trên KiotViet (PUT /products/{id}) — giữ nguyên tên/nhóm/
    đơn vị/giá (đọc bản hiện tại rồi PUT lại với code mới). Spike 2026-07-09 xác
    nhận PUT đổi code được. Ném RuntimeError nếu KiotViet từ chối."""
    cur = _request("GET", f"/products/{int(kv_id)}")
    body: dict = {
        "code": str(new_code or "").strip().upper(),
        "name": cur.get("name") or cur.get("fullName") or str(new_code),
        "categoryId": cur.get("categoryId"),
        "allowsSale": cur.get("allowsSale", True),
        "unit": cur.get("unit") or "cây",
    }
    if cur.get("basePrice"):
        body["basePrice"] = cur["basePrice"]
    return _request("PUT", f"/products/{int(kv_id)}", body=body)


def create_product_kv(code: str, name: str, *, category_id: int, unit: str = "",
                      base_price: float = 0) -> dict:
    """Tạo SP MỚI trên KiotViet (POST /products). Bắt buộc name/code/categoryId/
    allowsSale/unit (theo Public API). Trả {id, code, full_name}. Ném RuntimeError nếu
    KiotViet từ chối (vd nhóm hàng không tồn tại)."""
    code = (code or "").strip().upper()
    name = (name or code).strip()
    if not code:
        raise RuntimeError("Thiếu mã SP")
    if not category_id:
        raise RuntimeError("Thiếu nhóm hàng (categoryId)")
    body: dict = {
        "code": code, "name": name, "fullName": name,
        "categoryId": int(category_id), "allowsSale": True,
        "unit": unit or "cái",
    }
    if base_price:
        body["basePrice"] = base_price
    res = _request("POST", "/products", body=body)
    return {
        "id": res.get("id"),
        "code": (res.get("code") or code).strip(),
        "full_name": res.get("fullName") or res.get("name") or name,
    }
