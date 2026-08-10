import assert from "node:assert/strict";
import test from "node:test";
import { ALL_ITEMS, findMenuItem, itemAllowed } from "../src/homeMenu.ts";

// Trang đang mở → mục menu nào (dùng cho khối "Gần đây" ở #/home).
test("khớp đúng mục, kể cả khi đang ở trang con", () => {
  assert.equal(findMenuItem("#/kho")?.label, "Kho hàng");
  assert.equal(findMenuItem("#/kho/K10LV87")?.label, "Kho hàng");        // chi tiết SP
  assert.equal(findMenuItem("#/nhap-hang/12")?.label, "Nhập hàng");
  assert.equal(findMenuItem("#/viec/9?focus=comment:1")?.label, "Việc"); // bỏ query
});

// Bẫy tiền tố: startsWith trần trụi sẽ gán nhầm mục.
test("không nuốt tiền tố của route khác", () => {
  assert.equal(findMenuItem("#/kho-dau")?.label, "Kho đậu");
  assert.equal(findMenuItem("#/kho-dau/phieu/3")?.label, "Kho đậu");
  assert.equal(findMenuItem("#/tho")?.label, "Danh sách thợ");
  assert.equal(findMenuItem("#/thung/5"), null);      // thùng KHÔNG phải mục "Thợ"
  assert.equal(findMenuItem("#/khach/abc"), null);    // khách chi tiết ≠ "Kho hàng"
});

test("trang không thuộc mục nào thì trả null", () => {
  assert.equal(findMenuItem("#/order/503268"), null);
  assert.equal(findMenuItem("#/"), null);
  assert.equal(findMenuItem(""), null);
});

test("lọc theo quyền", () => {
  const luongThang = ALL_ITEMS.find((i) => i.href === "#/luong-thang")!;
  const users = ALL_ITEMS.find((i) => i.href === "#/users")!;
  const donHang = ALL_ITEMS.find((i) => i.href === "#/orders")!;
  assert.equal(itemAllowed(donHang, false, false), true);     // staff
  assert.equal(itemAllowed(luongThang, false, false), false); // cần văn phòng
  assert.equal(itemAllowed(luongThang, true, false), true);
  assert.equal(itemAllowed(users, true, false), false);       // cần admin
  assert.equal(itemAllowed(users, true, true), true);
});

test("mỗi mục 1 href duy nhất (khối Gần đây tra theo href)", () => {
  const hrefs = ALL_ITEMS.map((i) => i.href);
  assert.equal(new Set(hrefs).size, hrefs.length);
});
