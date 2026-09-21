export type SalesRange = { since: string; until: string };
export type SalesPresetKey = "today" | "week" | "month" | "30days" | "quarter" | "year" | "custom";
export type SalesFilterState = { period: SalesPresetKey; range: SalesRange };

export const SALES_FILTER_CACHE_KEY = "sales_dashboard_filter_v1";

const PRESETS: Exclude<SalesPresetKey, "custom">[] = ["today", "week", "month", "30days", "quarter", "year"];
const utcDate = (ymd: string) => new Date(`${ymd}T00:00:00Z`);
const ymd = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (s: string, days: number) => { const d = utcDate(s); d.setUTCDate(d.getUTCDate() + days); return ymd(d); };
export const startOfWeek = (s: string) => addDays(s, -((utcDate(s).getUTCDay() + 6) % 7));

export const todayVN = () => {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const get = (kind: string) => parts.find(p => p.type === kind)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")}`;
};

export const presetRange = (key: SalesPresetKey, today: string): SalesRange => {
  const d = utcDate(today), month = d.getUTCMonth();
  if (key === "today") return { since: today, until: today };
  if (key === "week") return { since: startOfWeek(today), until: today };
  if (key === "month") return { since: `${today.slice(0, 7)}-01`, until: today };
  if (key === "30days") return { since: addDays(today, -29), until: today };
  if (key === "quarter") return { since: `${d.getUTCFullYear()}-${String(Math.floor(month / 3) * 3 + 1).padStart(2, "0")}-01`, until: today };
  if (key === "year") return { since: `${today.slice(0, 4)}-01-01`, until: today };
  return { since: today, until: today };
};

const validYmd = (value: unknown): value is string => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return ymd(utcDate(value)) === value;
};
const validRange = (range: any): range is SalesRange =>
  validYmd(range?.since) && validYmd(range?.until) && range.since <= range.until;
const preset = (value: unknown): value is Exclude<SalesPresetKey, "custom"> => PRESETS.includes(value as any);

function resolve(period: unknown, range: any, today: string): SalesFilterState | null {
  if (preset(period)) return { period, range: presetRange(period, today) };
  if (period === "custom" && validRange(range)) return { period, range };
  return null;
}

/** URL có filter là nguồn chính; nếu URL trống thì khôi phục session cache. */
export function readSalesFilter(hash: string, cached: string | null, today: string): SalesFilterState {
  const params = new URLSearchParams(hash.split("?")[1] || "");
  const urlPeriod = params.get("period");
  if (urlPeriod) {
    return resolve(urlPeriod, { since: params.get("since"), until: params.get("until") }, today)
      || { period: "month", range: presetRange("month", today) };
  }
  if (cached) {
    try {
      const value = JSON.parse(cached);
      const restored = resolve(value?.period, value?.range, today);
      if (restored) return restored;
    } catch { /* cache cũ/hỏng → dùng mặc định */ }
  }
  return { period: "month", range: presetRange("month", today) };
}

export function salesFilterHash(state: SalesFilterState): string {
  const params = new URLSearchParams({ period: state.period });
  if (state.period === "custom") {
    params.set("since", state.range.since);
    params.set("until", state.range.until);
  }
  return `#/ban-hang?${params.toString()}`;
}
