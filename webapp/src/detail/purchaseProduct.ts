// Dựng danh sách gợi ý SP cho dòng phiếu nhập hàng + option "tạo mã hàng mới" khi
// mã gõ vào chưa có trong danh mục. Thuần (unit-test được), dùng chung
// PurchaseModal + PurchaseEdit. Tạo thật qua createProduct (POST /api/products).
import type { PickOpt } from "../ui/PickerPopup";

export const NEW_PROD_PREFIX = "__newprod__:";

export type ProdSearchResult = { code: string; name?: string; can_purchase?: boolean };

/** results (từ searchProducts) + query người dùng gõ → options cho PickerPopup.
 *  Chỉ SP "có thể nhập" (can_purchase !== false). Nếu mã gõ vào KHÔNG khớp mã nào,
 *  KHÔNG rỗng và KHÔNG phải toàn chữ số (backend cấm) → thêm option tạo mã hàng. */
export function buildPurchaseProductOptions(results: ProdSearchResult[], query: string): PickOpt[] {
  const opts: PickOpt[] = results
    .filter((s) => s.can_purchase !== false)
    .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }));
  const code = query.trim().toUpperCase();
  const exists = opts.some((o) => o.key.toUpperCase() === code);
  if (code && !/^\d+$/.test(code) && !exists) {
    opts.push({ key: NEW_PROD_PREFIX + code, label: `➕ Tạo mã hàng "${code}"` });
  }
  return opts;
}

export function isCreateProd(key: string): boolean {
  return key.startsWith(NEW_PROD_PREFIX);
}

export function codeFromCreateKey(key: string): string {
  return key.slice(NEW_PROD_PREFIX.length);
}
