import assert from "node:assert/strict";
import test from "node:test";
import { presetRange, rangeDays, validRange, vnToday } from "../src/detail/profitDates.ts";
import { aggregateProfit, grossMargin } from "../src/detail/profitChartData.ts";
import { profitParams, DEFAULT_FILTERS } from "../src/detail/profitFilters.ts";
const now = new Date("2026-09-10T05:00:00Z");
test("rolling presets count both ends without the legacy extra day", () => {
  for (const days of [7, 14, 30, 60, 90, 180, 365]) {
    const r = presetRange(`${days}days`, now);
    assert.equal(rangeDays(r), days);
    assert.equal(r.until, "2026-09-10");
  }
});
test("report day uses Vietnam even around UTC midnight", () => {
  assert.equal(vnToday(new Date("2026-09-09T18:30:00Z")), "2026-09-10");
  assert.deepEqual(presetRange("today", new Date("2026-09-09T16:59:00Z")), { since: "2026-09-09", until: "2026-09-09" });
});
test("weeks, quarters and years cross calendar boundaries", () => {
  const january = new Date("2026-01-01T05:00:00Z");
  assert.deepEqual(presetRange("last_week", january), { since: "2025-12-22", until: "2025-12-28" });
  assert.deepEqual(presetRange("this_week", january), { since: "2025-12-29", until: "2026-01-01" });
  assert.deepEqual(presetRange("last_quarter", january), { since: "2025-10-01", until: "2025-12-31" });
  assert.deepEqual(presetRange("this_quarter", now), { since: "2026-07-01", until: "2026-09-10" });
  assert.deepEqual(presetRange("last_year", january), { since: "2025-01-01", until: "2025-12-31" });
  assert.deepEqual(presetRange("last_month", january), { since: "2025-12-01", until: "2025-12-31" });
});
test("month picker can select historical leap-year months", () => {
  assert.deepEqual(presetRange("month_2024_2", now), { since: "2024-02-01", until: "2024-02-29" });
  assert.deepEqual(presetRange("month_2", now), { since: "2026-02-01", until: "2026-02-28" });
});
test("invalid and reversed dates cannot be submitted", () => {
  for (const r of [{ since: "", until: "2026-09-10" }, { since: "2026-02-30", until: "2026-03-01" },
    { since: "2026-09-10", until: "2026-09-09" }, { since: "2000-01-01", until: "2026-09-10" }]) assert.equal(validRange(r), false);
  assert.equal(validRange({ since: "2024-02-29", until: "2024-02-29" }), true);
});
test("chart groups use weighted margin and preserve totals across a year boundary", () => {
  const points = [
    { day: "2025-12-31", revenue: 100, cost: 50, profit: 50, real_profit: 40, loan: 10, orders: 1 },
    { day: "2026-01-01", revenue: 900, cost: 990, profit: -90, real_profit: -100, loan: 10, orders: 2 },
    { day: "2026-01-02", revenue: 0, cost: 0, profit: 0, real_profit: -10, loan: 10, orders: 0 },
  ];
  const weekly = aggregateProfit(points, "weekly");
  assert.equal(weekly.length, 1);
  assert.equal(weekly[0].day, "2025-12-29");
  assert.equal(weekly[0].real_profit, -70);
  assert.equal(weekly[0].orders, 3);
  assert.equal(grossMargin(weekly[0]), -4);
  assert.equal(grossMargin(points[2]), null);
  assert.deepEqual(aggregateProfit(points, "monthly").map(p => p.day), ["2025-12", "2026-01"]);
});
test("dashboard and orders can send the same combined filters", () => {
  const params = profitParams({ since: "2026-09-01", until: "2026-09-10" }, {
    ...DEFAULT_FILTERS, product: " sp1 ", customer: " Hoa ", profitability: "loss", payment: "unreceived",
  });
  assert.equal(params.get("product"), "SP1");
  assert.equal(params.get("customer"), "Hoa");
  assert.equal(params.get("profitability"), "loss");
  assert.equal(params.get("payment"), "unreceived");
  assert.equal(params.has("cost_status"), false);
});
test("filtered chart never turns unavailable company profit into zero", () => {
  const chart = aggregateProfit([
    { day: "2026-09-01", revenue: 100, cost: 60, profit: 40, loan: null, real_profit: null, cost_complete: true },
    { day: "2026-09-02", revenue: 100, cost: 0, profit: 0, loan: null, real_profit: null, cost_complete: false },
  ], "monthly");
  assert.equal(chart[0].real_profit, null);
  assert.equal(chart[0].loan, null);
  assert.equal(chart[0].profit, 40);
  assert.equal(grossMargin(chart[0]), null);
});
