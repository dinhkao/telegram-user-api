import assert from "node:assert/strict";
import test from "node:test";
import { fmtHourVN } from "../src/format.ts";

// LỖI CŨ: giờ báo cáo ảnh hiện bằng String(created_at).slice(11, 16) — server lưu
// UTC nên cắt thô ra SỚM 7 TIẾNG (chụp 14:05 giờ VN hiện thành 07:05).
// fmtHourVN phải luôn quy về Asia/Ho_Chi_Minh, không phụ thuộc múi giờ thiết bị.

test("ISO có Z: đổi sang giờ VN (UTC+7), không phải cắt chuỗi", () => {
  // 07:05 UTC = 14:05 giờ VN — đúng cái mà slice(11,16) làm sai
  assert.equal(fmtHourVN("2026-08-06T07:05:00Z"), "14:05");
  assert.equal("2026-08-06T07:05:00Z".slice(11, 16), "07:05");   // cách cũ: sai
});

test("ISO có offset +00:00 (định dạng server ghi báo cáo)", () => {
  assert.equal(fmtHourVN("2026-08-06T07:05:00+00:00"), "14:05");
});

test("'YYYY-MM-DD HH:MM:SS' không tz thì coi là UTC", () => {
  assert.equal(fmtHourVN("2026-08-06 07:05:00"), "14:05");
});

test("epoch giây (entity_images.created_at) — giờ chụp từng bức ảnh", () => {
  // 2026-08-06T07:05:00Z = 1785999900
  assert.equal(fmtHourVN(Date.parse("2026-08-06T07:05:00Z") / 1000), "14:05");
});

test("epoch mili-giây cũng nhận", () => {
  assert.equal(fmtHourVN(Date.parse("2026-08-06T07:05:00Z")), "14:05");
});

test("qua ngày: 23:30 UTC = 06:30 hôm sau giờ VN", () => {
  assert.equal(fmtHourVN("2026-08-06T23:30:00Z"), "06:30");
});

test("dùng đồng hồ 24h, không có SA/CH", () => {
  const s = fmtHourVN("2026-08-06T10:00:00Z");   // 17:00 giờ VN
  assert.equal(s, "17:00");
  assert.ok(!/SA|CH|AM|PM/i.test(s));
});

test("rỗng / không parse được → chuỗi rỗng, không ném lỗi", () => {
  assert.equal(fmtHourVN(""), "");
  assert.equal(fmtHourVN(null), "");
  assert.equal(fmtHourVN(undefined), "");
  assert.equal(fmtHourVN("khong-phai-ngay"), "");
  assert.equal(fmtHourVN(0), "");                 // 0 = chưa có giờ chụp (ảnh cũ)
});
