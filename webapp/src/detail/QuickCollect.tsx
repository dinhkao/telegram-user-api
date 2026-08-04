// THU NHANH đúng 1 đơn — khối trên cùng trang thu tiền (#/order/:id/thanh-toan).
// Mục đích: thu tiền trong 1 CHẠM. Chỉ thu ĐÚNG số còn nợ CỦA CHÍNH ĐƠN ĐANG MỞ,
// KHÔNG đụng nợ cũ và KHÔNG gom đơn khác của khách — muốn gộp thì dùng luồng chọn
// đơn + phân bổ ở dưới.
// CỐ Ý KHÔNG hỏi xác nhận: nút đã in rõ SỐ TIỀN + HÌNH THỨC ngay trên mặt nút, thêm
// một hộp thoại nữa là mất đúng cái nhanh mà nó sinh ra để có. Ghi nhầm thì admin xoá
// phiếu thu được (xem Payments/lịch sử đơn).
// Gọi cùng API với luồng gộp (bulkPayment → 1 phiếu KiotViet + 1 phiếu thu local),
// nên số liệu/audit không có đường đi riêng nào cả.
import { bulkPayment, type DebtOrder } from "../api";
import { money } from "../format";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

export function QuickCollect({ threadId, order, busy, setBusy, onDone }: {
  threadId: string;
  order: DebtOrder | null;        // đơn ĐANG MỞ trong danh sách còn nợ (null = hết nợ)
  busy: boolean;
  setBusy: (b: boolean) => void;
  onDone: () => Promise<void> | void;
}) {
  if (!order || order.debt <= 0) return null;

  const pay = async (method: "Cash" | "Transfer") => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await bulkPayment({
        source_thread_id: Number(threadId), method, amount: order.debt,
        allocations: [{ thread_id: order.thread_id, amount: order.debt }],
      });
      toast(`✅ Đã thu ${money(r.amount)} cho đơn này`, "ok");
      await onDone();
    } catch (ex: any) {
      toast(`❌ ${ex.message}`, "err");
      await onDone();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card qc-box">
      <div class="qc-head">
        <span><Icon name="zap" size={15} /> Thu nhanh đơn này</span>
        <span class="muted small">chỉ đơn đang mở · không gộp nợ cũ</span>
      </div>
      <button class="btn primary block qc-main" disabled={busy} onClick={() => pay("Cash")}>
        {busy ? "Đang thu…" : <>Thu tiền mặt <b>{money(order.debt)}đ</b></>}
      </button>
      <button class="btn block qc-alt" disabled={busy} onClick={() => pay("Transfer")}>
        Chuyển khoản {money(order.debt)}đ
      </button>
    </section>
  );
}
