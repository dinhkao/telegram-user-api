import assert from "node:assert/strict";
import test from "node:test";
import { presetRange, readSalesFilter, salesFilterHash } from "../src/detail/salesFilterState.ts";

const today = "2026-09-11";

test("URL filter overrides the cached sales period", () => {
  const cached = JSON.stringify({ period: "month", range: { since: "2026-09-01", until: today } });
  assert.deepEqual(readSalesFilter("#/ban-hang?period=today", cached, today), {
    period: "today", range: { since: today, until: today },
  });
});

test("sales period survives navigation through its URL", () => {
  const selected = { period: "week" as const, range: presetRange("week", today) };
  const hash = salesFilterHash(selected);
  assert.equal(hash, "#/ban-hang?period=week");
  assert.deepEqual(readSalesFilter(hash, null, today), selected);
});

test("sales filter falls back to session cache when URL has no period", () => {
  const cached = JSON.stringify({ period: "30days", range: { since: "old", until: "old" } });
  assert.deepEqual(readSalesFilter("#/ban-hang", cached, today), {
    period: "30days", range: { since: "2026-08-13", until: today },
  });
});

test("custom sales date range is preserved exactly", () => {
  const selected = { period: "custom" as const, range: { since: "2026-08-01", until: "2026-08-20" } };
  const hash = salesFilterHash(selected);
  assert.equal(hash, "#/ban-hang?period=custom&since=2026-08-01&until=2026-08-20");
  assert.deepEqual(readSalesFilter(hash, null, today), selected);
  assert.deepEqual(readSalesFilter("#/ban-hang", JSON.stringify(selected), today), selected);
});
