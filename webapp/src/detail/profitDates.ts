// Dùng ngày Việt Nam cho báo cáo; số ngày của preset tính cả hai đầu.
export type DateRange = { since: string; until: string };
const DAY = 86400000;
export const dateKey = (d: Date) => d.toISOString().slice(0, 10);
export const vnToday = (now = new Date()) => dateKey(new Date(now.getTime() + 7 * 3600000));
const utc = (s: string) => new Date(`${s}T00:00:00Z`);
export const shiftDay = (day: string, n: number) => dateKey(new Date(utc(day).getTime() + n * DAY));
export const rangeDays = (r: DateRange) => Math.round((utc(r.until).getTime() - utc(r.since).getTime()) / DAY) + 1;
export function validRange(r: DateRange): boolean {
  return [r.since, r.until].every(d => /^\d{4}-\d{2}-\d{2}$/.test(d) && !isNaN(utc(d).getTime()) && dateKey(utc(d)) === d)
    && r.since <= r.until && rangeDays(r) <= 3660;
}
export const displayDate = (s: string) => s.split("-").reverse().join("/");
export const displayRange = (r: DateRange) => r.since === r.until ? displayDate(r.since) : `${displayDate(r.since)} – ${displayDate(r.until)}`;
export function presetRange(p: string, now = new Date()): DateRange {
  const today = vnToday(now), d = utc(today), y = d.getUTCFullYear(), m = d.getUTCMonth();
  const month = (year: number, index: number, day = 1) => dateKey(new Date(Date.UTC(year, index, day)));
  const monday = shiftDay(today, -((d.getUTCDay() + 6) % 7));
  const quarter = Math.floor(m / 3) * 3;
  const rolling = /^(7|14|30|60|90|180|365)days$/.exec(p);
  if (rolling) return { since: shiftDay(today, 1 - Number(rolling[1])), until: today };
  switch (p) {
    case "yesterday": return { since: shiftDay(today, -1), until: shiftDay(today, -1) };
    case "this_week": return { since: monday, until: today };
    case "last_week": return { since: shiftDay(monday, -7), until: shiftDay(monday, -1) };
    case "this_month": return { since: month(y, m), until: today };
    case "last_month": return { since: month(y, m - 1), until: month(y, m, 0) };
    case "this_quarter": return { since: month(y, quarter), until: today };
    case "last_quarter": return { since: month(y, quarter - 3), until: month(y, quarter, 0) };
    case "this_year": return { since: month(y, 0), until: today };
    case "last_year": return { since: month(y - 1, 0), until: month(y, 0, 0) };
    default: {
      const fixed = /^month_(?:(\d{4})_)?(\d{1,2})$/.exec(p);
      if (fixed && Number(fixed[2]) >= 1 && Number(fixed[2]) <= 12) {
        const year = Number(fixed[1] || y), index = Number(fixed[2]) - 1;
        return { since: month(year, index), until: month(year, index + 1, 0) };
      }
      return { since: today, until: today };
    }
  }
}
export const QUICK_PRESETS = [
  ["today", "Hôm nay"], ["yesterday", "Hôm qua"], ["7days", "7 ngày"],
  ["30days", "30 ngày"], ["this_month", "Tháng này"], ["last_month", "Tháng trước"],
] as const;
export const MORE_PRESETS = [
  ["this_week", "Tuần này"], ["last_week", "Tuần trước"], ["14days", "14 ngày"],
  ["60days", "60 ngày"], ["90days", "90 ngày"], ["180days", "180 ngày"], ["365days", "365 ngày"],
  ["this_quarter", "Quý này"], ["last_quarter", "Quý trước"],
  ["this_year", "Năm nay"], ["last_year", "Năm trước"],
] as const;

export function initialProfitRange(fallback: string): DateRange {
  const p = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const r = { since: p.get("since") || "", until: p.get("until") || "" };
  return validRange(r) ? r : presetRange(fallback);
}
