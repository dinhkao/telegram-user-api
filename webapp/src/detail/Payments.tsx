// Khối thanh toán ở chi tiết đơn — LỊCH SỬ phiếu thu (xoá = admin) + nút mở trang
// Thu tiền (#/order/:id/thanh-toan, thu gộp nhiều đơn của khách). Tạo phiếu thu
// nằm ở trang riêng. Xoá phiếu thuộc 1 giao dịch gộp (payment_batch_id) → xoá CẢ
// giao dịch. POST /api/order/payment/delete.
import { useState } from "preact/hooks";
import { currentUser, isOffice, postJSON, setOrderBypassDebt } from "../api";
import { money, fmtDateTimeVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

export function Payments({ threadId, payments, hasCustomer, bypassDebt, onChanged }: { threadId: string; payments: any[]; hasCustomer: boolean; bypassDebt: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();   // chỉ văn phòng được thu tiền

  // Xoá 1 thanh toán — chỉ admin. Phiếu thuộc giao dịch gộp → xoá cả giao dịch.
  const del = async (p: any) => {
    if (!p.id) { toast("Thanh toán cũ không có id — xoá bằng lệnh Telegram /del_payment_", "err"); return; }
    const batch = !!p.payment_batch_id;
    const confirmMsg = batch
      ? "Xoá CẢ giao dịch thu gộp này?\n(Mọi đơn trong giao dịch sẽ bị gỡ thanh toán; xoá 1 phiếu KiotViet)"
      : `Xoá thanh toán ${money(p.amount)}?\n(Xoá khỏi đơn; KiotViet có thể phải xoá tay)`;
    if (!(await confirmDialog(confirmMsg, { danger: true }))) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await postJSON("/api/order/payment/delete", { thread_id: Number(threadId), payment_id: p.id });
      const base = batch ? "🗑️ Đã xoá giao dịch thu gộp" : `🗑️ Đã xoá thanh toán ${money(p.amount)}`;
      setMsg(r.kv_warning ? `${base} · ⚠️ ${r.kv_warning}` : base);
      onChanged();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  const goPay = () => {
    if (!hasCustomer) { toast("Đơn chưa gán khách — không thể thu tiền.", "err"); return; }
    window.location.hash = `#/order/${threadId}/thanh-toan`;
  };

  const toggleBypass = async () => {
    setBusy(true);
    try {
      await setOrderBypassDebt(threadId, !bypassDebt);
      toast(!bypassDebt ? "Đã ẩn đơn khỏi trang thu tiền" : "Đã đưa đơn lại vào trang thu tiền", "ok");
      onChanged();
    } catch (ex: any) {
      toast(ex?.message || "Không đổi được thiết lập", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="card">
      <b>Thanh toán</b>
      {payments.length > 0 ? (
        <ul class="payment-list">
          {payments.map((p, i) => (
            <li class="payment-item" key={i}>
              <div class="row space">
                <span>{p.code || p.method || "?"}{p.payment_batch_id ? " · gộp" : ""}</span>
                <span class="row" style="gap:6px;align-items:center">
                  <b>{money(p.amount)}</b>
                  {isAdmin && p.id ? <button class="btn small danger" disabled={busy} title="Xoá thanh toán" onClick={() => del(p)}><Icon name="trash" size={14} /></button> : null}
                </span>
              </div>
              {(p.createdBy || p.created_at) && (
                <div class="muted small">
                  {p.createdBy || "?"}{p.created_at ? ` · ${fmtDateTimeVN(p.created_at)}` : ""}
                </div>
              )}
              {p.old_debt != null && p.new_debt != null && (
                <div class="pay-debt small">Nợ: {money(p.old_debt)} → <b>{money(p.new_debt)}</b></div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p class="muted small">Chưa có thanh toán nào.</p>
      )}
      {msg && <p class="notice" onClick={() => setMsg("")}>{msg}</p>}
      {bypassDebt && (
        <p class="notice small"><Icon name="ban" size={14} /> Đơn này được ẩn khỏi trang thu tiền; trạng thái nợ vẫn giữ nguyên.</p>
      )}
      {office ? (
        <>
          <button class={"btn primary block" + (!hasCustomer || bypassDebt ? " faded" : "")}
            title={!hasCustomer ? "Đơn chưa gán khách" : bypassDebt ? "Đơn đang được ẩn khỏi trang thu tiền" : undefined}
            onClick={() => bypassDebt ? toast("Bật lại đơn trong trang thu tiền trước", "info") : goPay()}>
            <Icon name="banknote" size={16} /> Thu tiền
          </button>
          {payments.length === 0 && (
            <button class="btn block" disabled={busy} style={{ marginTop: "7px" }} onClick={toggleBypass}>
              <Icon name={bypassDebt ? "refresh" : "ban"} size={15} />
              {bypassDebt ? "Đưa lại vào trang thu tiền" : "Ẩn khỏi trang thu tiền"}
            </button>
          )}
        </>
      ) : (
        <p class="muted small">🔒 Chỉ văn phòng mới được thu tiền.</p>
      )}
    </div>
  );
}
