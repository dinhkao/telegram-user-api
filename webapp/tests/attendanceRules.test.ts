// Luật chấm công: chuẩn 4 lần/ngày, 2 lần chỉ hợp lệ khi cùng 1 buổi.
// Giữ ĐỒNG BỘ với tests/test_attendance_store.py::DayRuleTest (bản Python).
import assert from "node:assert/strict";
import test from "node:test";
import { dayError, dayIssues, sessionOf } from "../src/attendanceRules.ts";

test("đúng 4 lần = đạt chuẩn", () => {
  assert.equal(dayError(["07:00", "11:00", "13:00", "17:00"]), null);
});

test("không chấm lần nào = nghỉ, không phải lỗi", () => {
  assert.equal(dayError([]), null);
});

test("2 lần CÙNG buổi = làm nửa ngày, hợp lệ", () => {
  assert.equal(dayError(["07:00", "11:02"]), null);
  assert.equal(dayError(["13:00", "17:05"]), null);
  assert.equal(dayError(["13:00", "20:00"]), null);   // chiều + tăng ca tối
});

test("2 lần KHÁC buổi = lỗi (quên chấm trưa)", () => {
  const err = dayError(["07:00", "17:00"]);
  assert.ok(err && err.includes("2 buổi"));
});

test("1 hoặc 3 lần = thiếu", () => {
  for (const times of [["07:00"], ["07:00", "11:00", "13:00"]]) {
    const err = dayError(times);
    assert.ok(err && err.includes("thiếu"), times.join(","));
  }
});

test("hơn 4 lần = nhiều hơn chuẩn", () => {
  const err = dayError(["07:00", "11:00", "13:00", "17:00", "18:00", "20:00"]);
  assert.ok(err && err.includes("nhiều hơn"));
});

test("giờ chưa sắp xếp vẫn cùng kết luận", () => {
  assert.equal(dayError(["11:00", "07:00"]), null);
  assert.ok(dayError(["17:00", "07:00"])?.includes("2 buổi"));
});

test("sai số lần → CHỈ báo lỗi đó, không báo trùng cảnh báo", () => {
  assert.deepEqual(dayIssues(["07:00", "17:00"]).map((i) => i.level), ["err"]);
});

test("đủ 4 lần nhưng cặp quá gần → cảnh báo cam", () => {
  const issues = dayIssues(["07:00", "11:00", "13:40", "13:47"]);
  assert.deepEqual(issues.map((i) => i.level), ["warn"]);
  assert.ok(issues[0].text.includes("7ph"));
});

test("ngày sạch = không vấn đề gì", () => {
  assert.deepEqual(dayIssues(["07:00", "11:00", "13:00", "17:00"]), []);
});

test("buổi: trước 12:00 = sáng, từ 12:00 = chiều", () => {
  assert.equal(sessionOf("11:59"), "sang");
  assert.equal(sessionOf("12:00"), "chieu");
  assert.equal(sessionOf("20:30"), "chieu");
});
