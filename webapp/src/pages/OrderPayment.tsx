// Trang THU TIỀN của 1 đơn (#/order/:id/thanh-toan) — lấy khách của đơn + MỌI đơn
// của khách CHƯA có thanh toán (cũ→mới). Nhập 1 tổng tiền → tự phân bổ đơn cũ
// trước (trả đủ từng đơn, đơn cuối một phần). Xác nhận = 1 phiếu KiotViet, chia N
// phiếu thu local. POST /api/order/payment/bulk (cần mạng). Chỉ văn phòng.
import { useEffect, useMemo, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getPaymentContext, bulkPayment, isOffice, orderImageUrl, type PaymentContext, type DebtOrder } from "../api";
import { invalidateListCache } from "./OrdersList";
import { money, parseMoney, fmtDateTimeVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

/** Phân bổ đơn cũ trước — GIỐNG payment_store.domain.allocate_payment (server chốt lại). */
function allocate(orders: DebtOrder[], amount: number): Map<number, number> {
  const m = new Map<number, number>();
  let left = amount;
  for (const o of orders) {
    if (left <= 0) break;
    const take = Math.min(o.debt, left);
    if (take > 0) { m.set(o.thread_id, take); left -= take; }
  }
  return m;
}

export function OrderPayment({ threadId }: { threadId: string }) {
  const [ctx, setCtx] = useState<PaymentContext | null>(null);
  const [err, setErr] = useState("");
  const [amountStr, setAmountStr] = useState("");
  const [method, setMethod] = useState<"Cash" | "Transfer">("Cash");
  const [busy, setBusy] = useState(false);
  const office = isOffice();

  const reload = async () => {
    try { setCtx(await getPaymentContext(threadId)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, [threadId]);

  const goBack = () => { window.location.hash = `#/order/${threadId}`; };

  const amount = parseMoney(amountStr);
  const totalDebt = ctx?.total_debt || 0;
  const orders = ctx?.orders || [];
  const allocMap = useMemo(() => allocate(orders, amount), [orders, amount]);
  const overDebt = amount > totalDebt;
  const valid = amount > 0 && !overDebt && orders.length > 0;

  const confirm = async () => {
    if (!valid) return;
    const allocations = orders
      .map((o) => ({ thread_id: o.thread_id, amount: allocMap.get(o.thread_id) || 0 }))
      .filter((a) => a.amount > 0);
    const label = method === "Cash" ? "tiền mặt" : "chuyển khoản";
    if (!(await confirmDialog(
      `Thu ${money(amount)} (${label}) — chia vào ${allocations.length} đơn?`,
      { okLabel: "Thu tiền" }))) return;
    setBusy(true);
    try {
      const r = await bulkPayment({ source_thread_id: Number(threadId), method, amount, allocations });
      invalidateListCache();
      toast(`✅ Đã thu ${money(r.amount)} · chia ${r.allocations.length} đơn`, "ok");
      setAmountStr("");
      await reload();   // đơn vừa thu biến khỏi nhóm nợ
    } catch (ex: any) {
      // 409 = dữ liệu đổi đồng thời → yêu cầu tải lại
      toast(`❌ ${ex.message}`, "err");
      await reload();
    } finally {
      setBusy(false);
    }
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!ctx) return <Loading />;

  return (
    <div>
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div><div class="prod-sp big">Thu tiền · {ctx.customer.name}</div></div>
      </div>

      {!office ? (
        <div class="card muted small">🔒 Chỉ văn phòng mới được thu tiền.</div>
      ) : orders.length === 0 ? (
        <div class="card muted">Khách này không có đơn nào đang nợ (chưa có thanh toán).</div>
      ) : (
        <>
          <div class="card">
            <div class="row space">
              <span class="muted small">Tổng nợ ({orders.length} đơn chưa thu)</span>
              <b class="pay-total-debt">{money(totalDebt)}</b>
            </div>
            <div class="pay-box" style="margin-top:10px">
              <input inputMode="numeric" placeholder="Số tiền thu" value={amountStr}
                onInput={(e: any) => setAmountStr(e.target.value)} />
              <button type="button" class="pay-suggest" title="Điền toàn bộ nợ"
                onClick={() => setAmountStr(String(totalDebt))}>
                Toàn bộ nợ: {money(totalDebt)}
              </button>
            </div>
            {overDebt && <p class="notice err small">Số tiền vượt tổng nợ — tối đa {money(totalDebt)}.</p>}
            <div class="pay-method">
              <button class={"btn" + (method === "Cash" ? " primary" : "")} onClick={() => setMethod("Cash")}>
                <Icon name="banknote" size={16} /> Tiền mặt
              </button>
              <button class={"btn" + (method === "Transfer" ? " primary" : "")} onClick={() => setMethod("Transfer")}>
                <Icon name="bank" size={16} /> Chuyển khoản
              </button>
            </div>
          </div>

          <div class="card">
            <b>Phân bổ (đơn cũ trước)</b>
            <ul class="pay-alloc-list">
              {orders.map((o) => {
                const take = allocMap.get(o.thread_id) || 0;
                const icons = [...(o.task_icons || "")];
                return (
                  <li class={"pay-alloc" + (take > 0 ? " on" : "")} key={o.thread_id}>
                    <div class="pay-order-row">
                      <a class="pay-order-link" href={`#/order/${o.thread_id}`} onClick={(e: any) => e.stopPropagation()}>
                        {o.thumb_image_id ? (
                          <span class="pay-order-thumb-wrap">
                            <img class="pay-order-thumb" src={orderImageUrl(o.thread_id, o.thumb_image_id, "thumb")} loading="lazy" alt="" />
                            {(o.image_count || 0) > 1 && <span class="pay-order-more">+{(o.image_count || 0) - 1}</span>}
                          </span>
                        ) : (
                          <span class="pay-order-thumb pay-order-ph"><Icon name="receipt" size={22} /></span>
                        )}
                        <span class="pay-order-copy">
                          <span class="pay-order-text">{o.text || o.label || "(đơn không có nội dung)"}</span>
                          <span class="pay-order-icons" aria-label="Trạng thái đơn">
                            {icons.length ? icons.map((ic, i) => <span key={i}>{ic}</span>) : <span>······</span>}
                          </span>
                        </span>
                      </a>
                      <b class={take > 0 ? "pay-alloc-amt on" : "pay-alloc-amt"}>{take > 0 ? money(take) : "—"}</b>
                    </div>
                    <div class="row space muted small">
                      <span>{o.created ? fmtDateTimeVN(o.created) : ""}</span>
                      <span>Nợ đơn: {money(o.total)}{take > 0 && take < o.total ? ` · còn ${money(o.total - take)}` : ""}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <div class="card">
            <button class={"btn primary block" + (!valid || busy ? " faded" : "")} disabled={busy}
              onClick={() => (valid ? confirm() : toast(overDebt ? "Số tiền vượt tổng nợ" : "Nhập số tiền", "err"))}>
              {busy ? "Đang thu…" : `Thu ${amount > 0 ? money(amount) : ""} (${method === "Cash" ? "TM" : "CK"})`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
