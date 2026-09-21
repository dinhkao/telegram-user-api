export type ProfitFilters = { product: string; customer: string; payment: string; profitability: string; cost_status: string };
export const DEFAULT_FILTERS: ProfitFilters = { product: "", customer: "", payment: "all", profitability: "all", cost_status: "all" };
export const PAYMENT_OPTIONS = [["all", "Tất cả phiếu thu"], ["received", "Có phiếu thu"], ["unreceived", "Chưa có phiếu thu"]];
export const PROFIT_OPTIONS = [["all", "Tất cả mức lãi"], ["positive", "Có lãi"], ["loss", "Đang lỗ"], ["breakeven", "Hoà vốn"], ["low_margin", "Biên lãi từ 0 đến dưới 10%"]];
export const COST_OPTIONS = [["all", "Tất cả giá vốn"], ["complete", "Đủ giá vốn"], ["missing", "Thiếu giá vốn"]];
export const QUICK_FILTERS: { id: string; label: string; filters: Partial<ProfitFilters> }[] = [
  { id: "all", label: "Tất cả đơn", filters: {} },
  { id: "loss", label: "Đơn đang lỗ", filters: { profitability: "loss" } },
  { id: "low", label: "Biên lãi < 10%", filters: { profitability: "low_margin" } },
  { id: "missing", label: "Thiếu giá vốn", filters: { cost_status: "missing" } },
  { id: "unreceived", label: "Chưa có phiếu thu", filters: { payment: "unreceived" } },
  { id: "received", label: "Có phiếu thu", filters: { payment: "received" } },
];
export function profitParams(range: { since: string; until: string }, filters: ProfitFilters) {
  const params = new URLSearchParams(range);
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim() && value !== "all") params.set(key, key === "product" ? value.trim().toUpperCase() : value.trim());
  }
  return params;
}
