import { SolarDate } from "lunar-date-vn";

export type LunarDateLabel = {
  day: number;
  short: string;
  full: string;
};

const cache = new Map<string, LunarDateLabel | null>();

/** Format Vietnamese lunar date; N marks a leap lunar month (tháng nhuận). */
export function lunarDateLabel(date: Date): LunarDateLabel | null {
  const key = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
  const cached = cache.get(key);
  if (cached !== undefined) return cached;

  let lunar;
  try {
    lunar = new SolarDate(date).toLunarDate();
  } catch {
    lunar = null;
  }
  if (!lunar) {
    cache.set(key, null);
    return null;
  }

  const info = lunar.get();
  const isLeapMonth = !!info.leap_month;
  const leap = isLeapMonth ? "N" : "";
  const value = {
    day: info.day,
    short: `${info.day}/${info.month}${leap}`,
    full: `Âm lịch: ${info.day}/${info.month}/${info.year}${isLeapMonth ? " (tháng nhuận)" : ""}`,
  };
  cache.set(key, value);
  return value;
}
