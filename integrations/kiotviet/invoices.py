from __future__ import annotations

from .core import _request, log


def create_invoice(invoice_data: dict) -> dict:
    return _request("POST", "/invoices", body=invoice_data)


def get_invoices_by_order(order_code: str | int, limit: int = 10) -> list[dict]:
    result = _request("GET", "/invoices", query_params={"orderCode": str(order_code), "pageSize": limit})
    return result.get("data", [])


def get_invoice_detail(invoice_id: int) -> dict | None:
    return _request("GET", f"/invoices/{invoice_id}")


def delete_invoice_kv(invoice_id: int) -> bool:
    _request("DELETE", "/invoices", body={"id": invoice_id, "isVoidPayment": False})
    log.info("KiotViet invoice deleted: id=%d", invoice_id)
    return True


def build_invoice_details(invoice_items: list[dict], kv_ids: dict | None = None) -> list[dict]:
    """Item hoá đơn → invoiceDetails KiotViet. kv_ids = {MÃ_UPPER: kv_product_id}
    (product_store.kv_ids_for_items): SP đã link gửi productId (danh tính KiotViet
    BẤT BIẾN — đổi mã local không ảnh hưởng, spike 2026-07-09 xác nhận); SP chưa
    link / thiếu map → fallback productCode như cũ."""
    kv_ids = kv_ids or {}
    details = []
    for item in invoice_items:
        code = str(item.get("sp") or item.get("productCode") or "").strip().upper()
        detail = {
            "quantity": int(item.get("sl", item.get("quantity", 1))),
            "price": int(item.get("price", 0)),
            "note": str(item.get("note", "")) if item.get("note") else "",
        }
        pid = kv_ids.get(code)
        if pid:
            detail["productId"] = int(pid)
        else:
            detail["productCode"] = code or "test"
        details.append(detail)
    return details


def create_kiotviet_invoice(customer_id: int, invoice_items: list[dict], discount: int = 0,
                            pvc: int = 0, vat: int = 0, branch_id: int = 1133,
                            sold_by_id: int = 186250, kv_ids: dict | None = None) -> dict:
    invoice_details = build_invoice_details(invoice_items, kv_ids)
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
        surcharges.append({"id": 1000000298, "code": "THK000003", "price": pvc})
    if vat:
        surcharges.append({"id": 1865, "code": "THK000001", "price": vat})
    if surcharges:
        payload["surchages"] = surcharges
    log.info("Creating KiotViet invoice: cust=%d items=%d disc=%s pvc=%s vat=%s",
             customer_id, len(invoice_details), discount, pvc, vat)
    return _request("POST", "/invoices", body=payload)
