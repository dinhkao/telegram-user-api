import assert from "node:assert/strict";
import test from "node:test";
import type { InvProductSummary } from "../src/api.ts";
import { sortProductsByRecentChange } from "../src/pages/khoProducts.ts";

function product(code: string, at?: string | null): InvProductSummary {
  return {
    product_code: code,
    in_stock_total: 0,
    in_stock_count: 0,
    allocated_count: 0,
    shipped_count: 0,
    total_count: 0,
    last_changed_at: at,
  };
}

test("sản phẩm mới biến động được xếp lên trước, bất kể múi giờ ISO", () => {
  const shown = sortProductsByRecentChange([
    product("CU", "2026-07-15T12:00:00Z"),
    product("MOI", "2026-07-15T20:00:00+07:00"),
  ]);

  assert.deepEqual(shown.map((p) => p.product_code), ["MOI", "CU"]);
});

test("sản phẩm chưa có lịch sử nằm cuối và giữ thứ tự mã ổn định", () => {
  const shown = sortProductsByRecentChange([
    product("B"),
    product("GAN", "2026-07-15T12:00:00Z"),
    product("A", null),
  ]);

  assert.deepEqual(shown.map((p) => p.product_code), ["GAN", "A", "B"]);
});
