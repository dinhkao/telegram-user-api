// Logic thuần của Ô NHẬP TIỀN dùng chung (ui/MoneyEntryForm → format.ts):
// tách chữ số giữ được ô rỗng, và ĐỌC LẠI số tiền bằng chữ — dòng đọc lại là chỗ
// duy nhất người nhập bắt được lỗi thừa/thiếu số 0 trước khi lưu tiền lương.
import assert from "node:assert/strict";
import test from "node:test";
import { digitsOnly, docTien } from "../src/format.ts";

test("digitsOnly giữ ô rỗng, bóc mọi ký tự không phải số", () => {
  assert.equal(digitsOnly(""), "");
  assert.equal(digitsOnly("1.500.000đ"), "1500000");
  assert.equal(digitsOnly("abc"), "");
  assert.equal(digitsOnly("0"), "0");        // KHÁC rỗng: 0 là số người dùng gõ thật
});

test("docTien đọc theo triệu / nghìn / đồng", () => {
  assert.equal(docTien(500_000), "500 nghìn");
  assert.equal(docTien(1_500_000), "1 triệu 500 nghìn");
  assert.equal(docTien(12_000_000), "12 triệu");
  assert.equal(docTien(682_500), "682 nghìn 500 đồng");
  assert.equal(docTien(1_000_000), "1 triệu");
});

test("docTien trả rỗng với số không đọc được", () => {
  assert.equal(docTien(0), "");
  assert.equal(docTien(-1000), "");
  assert.equal(docTien(NaN), "");
  assert.equal(docTien(Infinity), "");
});
