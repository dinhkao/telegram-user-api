import assert from "node:assert/strict";
import test from "node:test";
import { lunarDateLabel } from "../src/detail/calendar/lunarDate.ts";

const localDate = (year: number, month: number, day: number) =>
  new Date(year, month - 1, day);

test("formats Tết 2024 as first lunar day", () => {
  assert.deepEqual(lunarDateLabel(localDate(2024, 2, 10)), {
    day: 1,
    short: "1/1",
    full: "Âm lịch: 1/1/2024",
  });
});

test("formats a normal Vietnamese lunar date", () => {
  assert.deepEqual(lunarDateLabel(localDate(2024, 6, 15)), {
    day: 10,
    short: "10/5",
    full: "Âm lịch: 10/5/2024",
  });
});

test("marks the leap sixth lunar month in 2025", () => {
  assert.deepEqual(lunarDateLabel(localDate(2025, 7, 25)), {
    day: 1,
    short: "1/6N",
    full: "Âm lịch: 1/6/2025 (tháng nhuận)",
  });
});

test("hides unsupported dates instead of showing zeroes", () => {
  assert.equal(lunarDateLabel(localDate(2300, 1, 1)), null);
});
