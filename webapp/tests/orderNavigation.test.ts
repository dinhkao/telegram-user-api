import assert from "node:assert/strict";
import test from "node:test";
import type { OrderRow } from "../src/detail/OrderCards.tsx";
import { applyCustomerOrderChange } from "../src/pages/orderNavigation.ts";

function row(threadId: number, customerKey?: string, taskIcons = "······"): OrderRow {
  return { thread_id: threadId, customer_key: customerKey, task_icons: taskIcons } as OrderRow;
}

test("vá trạng thái realtime của đơn cùng khách đang có trong nav", () => {
  const before = [row(30, "kh-1"), row(20, "kh-1")];
  const changed = row(20, "kh-1", "✅✅❌❌❌😡");

  const after = applyCustomerOrderChange(before, "kh-1", { thread_id: "20", row: changed });

  assert.equal(after[1], changed);
  assert.equal(after[1].task_icons, "✅✅❌❌❌😡");
});

test("thêm và sắp đúng đơn vừa được gán vào khách", () => {
  const before = [row(30, "kh-1"), row(10, "kh-1")];
  const added = row(20, "kh-1");

  const after = applyCustomerOrderChange(before, "kh-1", { thread_id: "20", row: added });

  assert.deepEqual(after.map((item) => item.thread_id), [30, 20, 10]);
});

test("xóa khỏi nav khi đơn bị xóa hoặc chuyển sang khách khác", () => {
  const before = [row(30, "kh-1"), row(20, "kh-1")];

  const reassigned = applyCustomerOrderChange(before, "kh-1", {
    thread_id: "20",
    row: row(20, "kh-2"),
  });
  const deleted = applyCustomerOrderChange(before, "kh-1", { thread_id: "20", row: null });

  assert.deepEqual(reassigned.map((item) => item.thread_id), [30]);
  assert.deepEqual(deleted.map((item) => item.thread_id), [30]);
});

test("tương thích payload server cũ chưa có customer_key", () => {
  const before = [row(20, "kh-1")];
  const legacyChanged = row(20, undefined, "✅·····");
  const unrelated = row(10, undefined);

  const patched = applyCustomerOrderChange(before, "kh-1", { thread_id: "20", row: legacyChanged });
  const ignored = applyCustomerOrderChange(before, "kh-1", { thread_id: "10", row: unrelated });

  assert.equal(patched[0], legacyChanged);
  assert.equal(ignored, before);
});
