import type { InvProductSummary } from "../api";

function changedAtMs(p: InvProductSummary): number {
  if (!p.last_changed_at) return 0;
  const ms = Date.parse(p.last_changed_at);
  return Number.isFinite(ms) ? ms : 0;
}

/** Mới biến động tồn lên trước; dữ liệu chưa có mốc xếp theo mã để ổn định. */
export function sortProductsByRecentChange(products: InvProductSummary[]): InvProductSummary[] {
  return products.slice().sort((a, b) =>
    changedAtMs(b) - changedAtMs(a) ||
    a.product_code.localeCompare(b.product_code, "vi")
  );
}
