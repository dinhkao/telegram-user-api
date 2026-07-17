// Dựng danh sách gợi ý SP cho dòng phiếu nhập hàng + option "tạo mã hàng mới" khi
// mã gõ vào chưa có trong danh mục. Thuần (unit-test được), dùng chung
// PurchaseCreate + PurchaseEdit. Tạo thật qua createProduct (POST /api/products).
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

// ── ĐƠN VỊ NHẬP của 1 SP: đơn vị gốc (factor 1) + các đơn vị quy đổi (product_units)
// + VAI 📦 nguyên kiện. 1 fetch listProductUnits/mã, cache module — dùng chung
// PurchaseCreate + PurchaseEdit + PurchaseGoodsModal.
export type UnitChoice = { name: string; factor: number };
export type BulkRole = { name: string; factor: number };
type UnitInfo = { base_unit: string; units: { id: number; name: string; factor: number }[];
                  roles: { bulk_unit_id: number | null } };
const _infoCache = new Map<string, Promise<UnitInfo | null>>();

function unitInfoFor(code: string): Promise<UnitInfo | null> {
  const key = code.trim().toUpperCase();
  if (!key) return Promise.resolve(null);
  let p = _infoCache.get(key);
  if (!p) {
    p = import("../api").then((api) => api.listProductUnits(key))
      .catch(() => { _infoCache.delete(key); return null; });   // SP ngoài danh mục
    _infoCache.set(key, p);
  }
  return p;
}

export function unitChoicesFor(code: string): Promise<UnitChoice[]> {
  return unitInfoFor(code).then((d) => d
    ? [{ name: d.base_unit || "cây", factor: 1 }, ...d.units.map((u) => ({ name: u.name, factor: u.factor }))]
    : []);
}

/** Vai 📦 NGUYÊN KIỆN của SP → {name, factor} | null. Nhập đúng kiện = thùng tự
 *  dán nhãn đơn vị, khỏi chọn đơn vị chứa (server enforce cùng luật). */
export function bulkRoleFor(code: string): Promise<BulkRole | null> {
  return unitInfoFor(code).then((d) => {
    const rid = d?.roles?.bulk_unit_id;
    if (d == null || rid === null || rid === undefined) return null;
    if (rid === 0) return { name: d.base_unit || "cây", factor: 1 };
    const u = d.units.find((x) => x.id === rid);
    return u ? { name: u.name, factor: u.factor } : null;
  });
}

/** Thêm đơn vị quy đổi cho SP ngay từ dòng phiếu nhập (PurchaseUnitPicker):
 *  POST product_units rồi nạp lại danh sách (cache invalidate → mọi dòng cùng mã
 *  thấy đơn vị mới). factor = 1 đơn vị mới bằng bao nhiêu đơn vị gốc. */
export async function addUnitChoice(code: string, name: string, factor: number): Promise<UnitChoice[]> {
  const key = code.trim().toUpperCase();
  const api = await import("../api");
  await api.addProductUnit(key, name, factor);
  _infoCache.delete(key);
  return unitChoicesFor(key);
}
