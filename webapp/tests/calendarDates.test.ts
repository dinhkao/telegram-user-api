import assert from "node:assert/strict";
import test from "node:test";
import { addMonths, continuousDays, dateKey } from "../src/detail/calendar/calendarDates.ts";

test("addMonths crosses year boundaries", () => {
  assert.deepEqual(addMonths({ y: 2025, m: 11 }, 1), { y: 2026, m: 0 });
  assert.deepEqual(addMonths({ y: 2025, m: 0 }, -1), { y: 2024, m: 11 });
});

test("continuousDays returns complete Monday-to-Sunday weeks", () => {
  const days = continuousDays({ y: 2024, m: 0 }, { y: 2024, m: 0 });
  assert.equal(dateKey(days[0]), "2024-01-01");
  assert.equal(dateKey(days.at(-1)!), "2024-02-04");
  assert.equal(days.length, 35);
});

test("dateKey pads month and day", () => {
  assert.equal(dateKey(new Date(2026, 0, 5)), "2026-01-05");
});
