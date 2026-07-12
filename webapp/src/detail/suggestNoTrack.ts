// Gợi ý 'Bỏ theo dõi nợ' đơn cũ — gọi sau khi bước 'Nhận tiền / Gửi toa cho
// khách' xong (Tasks.tsx). GET /api/order/{id}/debt-suggest → nếu khách còn đơn
// CŨ đang 😡 thì confirm; đồng ý → POST /api/order/no-track từng đơn (😑).
// Lỗi mạng/endpoint chưa có → im lặng, không cản flow đánh dấu task.
import { getJSON, postJSON } from "../api";
import { confirmDialog, toast } from "../ui/feedback";
import { money } from "../format";

type SuggestOrder = { thread_id: number; created?: string; text?: string; total?: number };

const dmy = (iso?: string) => {
  const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : "";
};

export async function suggestNoTrackOldOrders(threadId: string | number): Promise<void> {
  let orders: SuggestOrder[] = [];
  try {
    const r = await getJSON(`/api/order/${threadId}/debt-suggest`);
    orders = r?.orders || [];
  } catch {
    return;
  }
  if (!orders.length) return;
  const lines = orders
    .map((o) => `• ${dmy(o.created)} · ${(o.text || `#${o.thread_id}`).slice(0, 34)}${o.total ? ` · ${money(o.total)}` : ""}`)
    .join("\n");
  const ok = await confirmDialog(
    `Khách này còn ${orders.length} đơn CŨ đang theo dõi nợ 😡:\n${lines}\n\nBỏ theo dõi nợ (😑) các đơn cũ này?`,
    { okLabel: "Bỏ theo dõi", cancelLabel: "Giữ nguyên" },
  );
  if (!ok) return;
  let done = 0;
  for (const o of orders) {
    try {
      await postJSON("/api/order/no-track", { thread_id: o.thread_id, on: true });
      done++;
    } catch { /* đơn lỗi thì bỏ qua, báo tổng ở toast */ }
  }
  if (done === orders.length) toast(`😑 Đã bỏ theo dõi nợ ${done} đơn cũ`, "ok");
  else toast(`Bỏ theo dõi ${done}/${orders.length} đơn — thử lại đơn còn lại`, "err");
}
