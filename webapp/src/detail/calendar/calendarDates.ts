import type { Ym } from "./types";

export const pad = (n: number) => String(n).padStart(2, "0");

export const addMonths = ({ y, m }: Ym, amount: number): Ym => {
  const date = new Date(y, m + amount, 1);
  return { y: date.getFullYear(), m: date.getMonth() };
};

export const ymLte = (a: Ym, b: Ym) =>
  a.y < b.y || (a.y === b.y && a.m <= b.m);

export const ymStr = ({ y, m }: Ym) => `${y}-${pad(m + 1)}`;

export const dateKey = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** Full weeks from Monday around the first month through Sunday after the last. */
export function continuousDays(from: Ym, to: Ym): Date[] {
  const start = new Date(from.y, from.m, 1);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));

  const end = new Date(to.y, to.m + 1, 0);
  end.setDate(end.getDate() + (6 - ((end.getDay() + 6) % 7)));

  const days: Date[] = [];
  for (let date = new Date(start); date <= end && days.length < 20000; date.setDate(date.getDate() + 1)) {
    days.push(new Date(date));
  }
  return days;
}
