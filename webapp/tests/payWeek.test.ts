import assert from "node:assert/strict";
import test from "node:test";
import { isoDate, payWeek } from "../src/format.ts";

// Tuần lương = thứ 7 tuần trước → thứ 6 tuần này (đúng 7 ngày, chốt vào thứ 6).
test("payWeek chạy từ thứ 7 tuần trước tới thứ 6 tuần này", () => {
  // 2026-07-24 là thứ 6 → kỳ mở thứ 7 18/07
  assert.deepEqual(payWeek(0, new Date(2026, 6, 24)), { from: "2026-07-18", to: "2026-07-24" });
});

test("ngày khác thứ 6 thì lấy tuần lương vừa khép, không lấn tương lai", () => {
  // 2026-07-25 thứ 7 + 2026-07-30 thứ 5 → vẫn là kỳ khép hôm 24/07
  assert.deepEqual(payWeek(0, new Date(2026, 6, 25)), { from: "2026-07-18", to: "2026-07-24" });
  assert.deepEqual(payWeek(0, new Date(2026, 6, 30)), { from: "2026-07-18", to: "2026-07-24" });
  // 2026-07-21 thứ 3 → kỳ khép hôm 17/07
  assert.deepEqual(payWeek(0, new Date(2026, 6, 21)), { from: "2026-07-11", to: "2026-07-17" });
});

test("mốc chốt không bao giờ vượt hôm nay", () => {
  for (let i = 0; i < 14; i++) {
    const day = new Date(2026, 6, 20 + i);
    assert.ok(payWeek(0, day).to <= isoDate(day), `to vượt hôm nay ở ${isoDate(day)}`);
  }
});

test("back = 1 lùi đúng 1 tuần", () => {
  assert.deepEqual(payWeek(1, new Date(2026, 6, 24)), { from: "2026-07-11", to: "2026-07-17" });
});

test("hai kỳ liên tiếp nối nhau, KHÔNG đè ngày nào", () => {
  for (let i = 0; i < 14; i++) {
    const day = new Date(2026, 6, 20 + i);
    const cur = payWeek(0, day), prev = payWeek(1, day);
    const gap = (Date.parse(cur.from) - Date.parse(prev.to)) / 86400000;
    assert.equal(gap, 1, `kỳ ${prev.to} → ${cur.from} phải liền nhau, không trùng ngày`);
  }
});

test("mốc đúng thứ 7 → thứ 6 và dài đúng 7 ngày", () => {
  for (let i = 0; i < 14; i++) {
    const { from, to } = payWeek(0, new Date(2026, 6, 1 + i));
    assert.equal(new Date(from + "T00:00:00").getDay(), 6, `from ${from} phải là thứ 7`);
    assert.equal(new Date(to + "T00:00:00").getDay(), 5, `to ${to} phải là thứ 6`);
    const days = (Date.parse(to) - Date.parse(from)) / 86400000 + 1;
    assert.equal(days, 7);
  }
});

test("qua mốc tháng/năm vẫn đúng", () => {
  // 2027-01-01 là thứ 6 (mốc chốt = chính hôm đó), kỳ mở thứ 7 26/12/2026
  assert.deepEqual(payWeek(0, new Date(2027, 0, 1)), { from: "2026-12-26", to: "2027-01-01" });
});
