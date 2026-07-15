import type { OrderRow } from "../detail/OrderCards";

type OrderChanged = { thread_id: string; row: OrderRow | null };

/**
 * Vá danh sách nav cùng khách từ payload realtime.
 * customer_key được server gửi để xử lý đúng cả trường hợp đổi khách; payload từ
 * server cũ chưa có field này vẫn được phép vá một dòng đã tồn tại.
 */
export function applyCustomerOrderChange(
  orders: OrderRow[],
  customerKey: string,
  event: OrderChanged,
): OrderRow[] {
  if (!customerKey) return orders;

  const index = orders.findIndex((order) => String(order.thread_id) === event.thread_id);
  if (event.row === null) {
    return index < 0 ? orders : orders.filter((_, i) => i !== index);
  }

  const rowKey = event.row.customer_key;
  const membershipKnown = rowKey !== undefined && rowKey !== null;
  const belongsToCustomer = membershipKnown ? String(rowKey) === customerKey : index >= 0;

  if (!belongsToCustomer) {
    return index < 0 ? orders : orders.filter((_, i) => i !== index);
  }

  if (index >= 0) {
    const next = orders.slice();
    next[index] = event.row;
    return next;
  }

  // API đơn cùng khách sắp mới→cũ theo thread_id; giữ đúng thứ tự khi một đơn vừa
  // được tạo/gán vào khách này ở máy khác.
  return [...orders, event.row].sort((a, b) => Number(b.thread_id) - Number(a.thread_id));
}
