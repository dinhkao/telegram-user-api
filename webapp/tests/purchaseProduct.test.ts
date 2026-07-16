import assert from "node:assert/strict";
import test from "node:test";
import { buildPurchaseProductOptions, isCreateProd, codeFromCreateKey, NEW_PROD_PREFIX } from "../src/detail/purchaseProduct.ts";

test("mã đã có → không có option tạo mới", () => {
  const opts = buildPurchaseProductOptions([{ code: "K10", name: "Kẹo 10" }], "k10");
  assert.equal(opts.some((o) => isCreateProd(o.key)), false);
});

test("mã lạ → có option tạo mới ở cuối, chữ HOA", () => {
  const opts = buildPurchaseProductOptions([{ code: "K10" }], "moi-2");
  const last = opts[opts.length - 1];
  assert.ok(isCreateProd(last.key));
  assert.equal(codeFromCreateKey(last.key), "MOI-2");
  assert.ok(last.label.includes("MOI-2"));
});

test("mã toàn chữ số → không cho tạo (backend cấm)", () => {
  const opts = buildPurchaseProductOptions([], "123");
  assert.equal(opts.some((o) => isCreateProd(o.key)), false);
});

test("SP can_purchase=false bị lọc khỏi gợi ý", () => {
  const opts = buildPurchaseProductOptions([{ code: "NOPE", can_purchase: false }], "");
  assert.equal(opts.length, 0);
});
