import assert from "node:assert/strict";
import test from "node:test";
import { normTime, isTimeOk } from "../src/format.ts";

// Gương của tests/test_production_time_fmt.py — 2 bên phải ra CÙNG kết quả.
const CASES: [string, string][] = [
  ["07:00", "07:00"], ["7:04", "07:04"], ["7h", "07:00"], ["13h40", "13:40"],
  ["9h5", "09:05"], ["13g40", "13:40"], ["13h 30", "13:30"], ["15h35p", "15:35"],
  ["1415", "14:15"], ["730", "07:30"], ["10", "10:00"], ["15:00_", "15:00"],
  ["7.30", "07:30"], ["7,30", "07:30"], ["09g50", "09:50"], ["11G", "11:00"],
  ["4h15", "16:15"], ["1", "13:00"], ["5h40", "17:40"], ["12h", "12:00"], ["", ""],
];

test("normTime quy mọi kiểu ghi về HH:MM", () => {
  for (const [raw, want] of CASES) assert.equal(normTime(raw), want, raw);
});

test("không hiểu → giữ nguyên + isTimeOk false", () => {
  for (const raw of ["abc", "25h", "7h75", "12345", "sáng"]) {
    assert.equal(normTime(raw), raw);
    assert.equal(isTimeOk(raw), false);
  }
  assert.equal(isTimeOk(""), true);
  assert.equal(isTimeOk("7h"), true);
});
