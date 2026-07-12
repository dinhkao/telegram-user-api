// Trang THU TIỀN của 1 đơn (#/order/:id/thanh-toan) — lấy khách của đơn + MỌI đơn
// của khách CHƯA có thanh toán. Người dùng CHỌN các đơn muốn thu, nhập tổng tiền
// → phân bổ theo chiều sắp xếp đang chọn (mặc định mới→cũ; trả đủ từng đơn, đơn
// cuối một phần). Xác nhận = 1 phiếu KiotViet, chia N phiếu thu local.
// POST /api/order/payment/bulk (cần mạng). Chỉ văn phòng.
// Mỗi đơn có nút ẨN khỏi trang thu tiền (bypass_debt) — toggle 2 chiều: đơn ẩn rơi
// xuống mục "Đã ẩn" và không được phân bổ; bấm "Đưa lại" để thu tiếp.
import { useEffect, useMemo, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getPaymentContext, bulkPayment, isOffice, orderImageUrl, setOrderBypassDebt, type PaymentContext, type DebtOrder } from "../api";
import { invalidateListCache } from "./OrdersList";
import { money, parseMoney, fmtDateTimeVN, fmtRelative } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

/** Phân bổ lần lượt theo thứ tự danh sách đang hiển thị. */
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
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [newestFirst, setNewestFirst] = useState(true);
  const [busy, setBusy] = useState(false);
  const [hidingSelected, setHidingSelected] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);  // đơn đang đổi ẩn/hiện
  const [hiddenOpen, setHiddenOpen] = useState(false);
  const office = isOffice();

  const reload = async () => {
    try {
      const next = await getPaymentContext(threadId);
      setCtx(next);
      const available = new Set(next.orders.map((o) => o.thread_id));
      setSelectedIds((prev) => new Set([...prev].filter((id) => available.has(id))));
      setErr("");
    }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => {
    setSelectedIds(new Set());
    setAmountStr("");
    setNewestFirst(true);
    reload();
  }, [threadId]);

  const amount = parseMoney(amountStr);
  const rawCustomerDebt = Number(ctx?.customer.debt ?? 0);
  const customerDebt = Number.isFinite(rawCustomerDebt) ? rawCustomerDebt : 0;
  const orders = ctx?.orders || [];
  const hiddenOrders = ctx?.hidden_orders || [];
  // API trả cũ→mới; giao diện mặc định đảo lại để thao tác trên đơn mới nhất trước.
  const orderedOrders = useMemo(
    () => newestFirst ? [...orders].reverse() : orders,
    [orders, newestFirst],
  );
  const selectedOrders = useMemo(
    () => orderedOrders.filter((o) => selectedIds.has(o.thread_id)),
    [orderedOrders, selectedIds],
  );
  const selectedDebt = selectedOrders.reduce((sum, o) => sum + o.debt, 0);
  const payableDebt = Math.min(selectedDebt, Math.max(0, customerDebt));
  const allocMap = useMemo(() => allocate(selectedOrders, amount), [selectedOrders, amount]);
  const overCustomerDebt = amount > Math.max(0, customerDebt);
  const overSelectedDebt = amount > selectedDebt;
  const overDebt = overCustomerDebt || overSelectedDebt;
  const valid = amount > 0 && selectedOrders.length > 0 && !overDebt;

  const toggleSelect = (tid: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(tid)) next.delete(tid);
      else next.add(tid);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(selectedIds.size === orders.length
      ? new Set()
      : new Set(orders.map((o) => o.thread_id)));
  };

  // Ẩn / đưa-lại 1 đơn ngay trên trang thu tiền → tải lại danh sách (tổng nợ đổi theo).
  const toggleHide = async (tid: number, hide: boolean) => {
    setTogglingId(tid);
    try {
      await setOrderBypassDebt(tid, hide);
      toast(hide ? "Đã ẩn đơn khỏi trang thu tiền" : "Đã đưa đơn lại vào trang thu tiền", "ok");
      await reload();
    } catch (ex: any) {
      toast(ex?.message || "Không đổi được thiết lập", "err");
    } finally { setTogglingId(null); }
  };

  const hideSelected = async () => {
    const ids = selectedOrders.map((o) => o.thread_id);
    if (!ids.length || hidingSelected) return;
    if (!(await confirmDialog(
      `Ẩn ${ids.length} đơn đã chọn khỏi trang thu tiền? Bạn vẫn có thể đưa lại từ mục “Đã ẩn”.`,
      { okLabel: "Ẩn đơn", danger: true },
    ))) return;

    setHidingSelected(true);
    const hidden = new Set<number>();
    try {
      for (const tid of ids) {
        try {
          await setOrderBypassDebt(tid, true);
          hidden.add(tid);
        } catch { /* tiếp tục các đơn còn lại; báo tổng lỗi ở cuối */ }
      }
      setSelectedIds((prev) => new Set([...prev].filter((id) => !hidden.has(id))));
      if (hidden.size === ids.length) setAmountStr("");
      setHiddenOpen(true);
      await reload();
      if (hidden.size === ids.length) toast(`Đã ẩn ${hidden.size} đơn khỏi trang thu tiền`, "ok");
      else toast(`Đã ẩn ${hidden.size}/${ids.length} đơn · ${ids.length - hidden.size} đơn bị lỗi`, "err");
    } finally {
      setHidingSelected(false);
    }
  };

  const confirm = async () => {
    if (!valid) return;
    const allocations = selectedOrders
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

  // Khối ảnh + text + icon trạng thái của 1 đơn — dùng chung cho danh sách phân bổ
  // lẫn danh sách "Đã ẩn" (khỏi lệch khi 1 chỗ đổi).
  const orderLink = (o: DebtOrder) => {
    const icons = [...(o.task_icons || "")];
    return (
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
    );
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
      ) : orders.length === 0 && hiddenOrders.length === 0 ? (
        <div class="card muted">Khách này không có đơn nào đang nợ (chưa có thanh toán).</div>
      ) : (
        <>
          {orders.length > 0 ? (
            <>
              <div class="card">
                <div class="row space">
                  <span class="muted small">Tổng nợ khách</span>
                  <b class="pay-total-debt">{money(customerDebt)}</b>
                </div>
                <div class="pay-box" style="margin-top:10px">
                  <input inputMode="numeric" placeholder="Số tiền thu" value={amountStr}
                    onInput={(e: any) => setAmountStr(e.target.value)} />
                  <button type="button" class="pay-suggest" title="Điền toàn bộ nợ của các đơn đã chọn"
                    disabled={selectedOrders.length === 0 || payableDebt <= 0}
                    onClick={() => setAmountStr(String(payableDebt))}>
                    Thu tối đa đơn đã chọn: {money(payableDebt)}
                  </button>
                </div>
                {selectedOrders.length === 0 && <p class="notice small">Chọn ít nhất một đơn ở bên dưới.</p>}
                {selectedOrders.length > 0 && customerDebt <= 0 && <p class="notice small">Khách hiện không còn công nợ.</p>}
                {selectedOrders.length > 0 && customerDebt > 0 && overCustomerDebt && <p class="notice err small">Số tiền vượt tổng nợ khách — tối đa {money(customerDebt)}.</p>}
                {selectedOrders.length > 0 && !overCustomerDebt && overSelectedDebt && <p class="notice err small">Số tiền vượt nợ của các đơn đã chọn — tối đa {money(selectedDebt)}.</p>}
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
                <div class="pay-select-head">
                  <div class="pay-select-copy">
                    <b>Chọn đơn nhận thanh toán</b>
                    <span class="muted small">Đã chọn {selectedOrders.length}/{orders.length} · {money(selectedDebt)}</span>
                  </div>
                  <div class="pay-select-actions">
                    <button type="button" class="pay-sort" onClick={() => setNewestFirst((v) => !v)}
                      title="Đổi chiều sắp xếp" aria-label={`Đang xếp ${newestFirst ? "mới nhất trước" : "cũ nhất trước"}. Bấm để đổi chiều`}>
                      <Icon name="sort" size={14} /> {newestFirst ? "Mới trước" : "Cũ trước"}
                    </button>
                    <button type="button" class="pay-select-all" onClick={toggleSelectAll}>
                      {selectedIds.size === orders.length ? "Bỏ chọn" : "Chọn tất cả"}
                    </button>
                  </div>
                </div>
                {selectedOrders.length > 0 && (
                  <button type="button" class="pay-hide-selected" disabled={hidingSelected}
                    onClick={hideSelected}>
                    <Icon name="ban" size={15} />
                    {hidingSelected ? "Đang ẩn…" : `Ẩn ${selectedOrders.length} đơn đã chọn khỏi thu tiền`}
                  </button>
                )}
                <ul class="pay-alloc-list">
                  {orderedOrders.map((o) => {
                    const selected = selectedIds.has(o.thread_id);
                    const take = allocMap.get(o.thread_id) || 0;
                    return (
                      <li class={"pay-alloc" + (selected ? " selected" : "") + (take > 0 ? " on" : "")} key={o.thread_id}>
                        <div class="pay-order-row">
                          <label class="pay-order-check" title={selected ? "Bỏ chọn đơn" : "Chọn đơn nhận thanh toán"}>
                            <input type="checkbox" checked={selected}
                              aria-label={`${selected ? "Bỏ chọn" : "Chọn"} đơn #${o.thread_id}`}
                              onChange={() => toggleSelect(o.thread_id)} />
                            <span aria-hidden="true"><Icon name="check" size={14} /></span>
                          </label>
                          {orderLink(o)}
                          <b class={take > 0 ? "pay-alloc-amt on" : "pay-alloc-amt"}>
                            {take > 0 ? money(take) : selected ? money(0) : "—"}
                          </b>
                          <button class="pay-hide" disabled={togglingId === o.thread_id}
                            title="Ẩn đơn khỏi trang thu tiền" aria-label="Ẩn đơn khỏi trang thu tiền"
                            onClick={() => toggleHide(o.thread_id, true)}>
                            <Icon name="ban" size={16} />
                          </button>
                        </div>
                        <div class="row space muted small">
                          <span>{o.created ? <>{fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : ""}</span>
                          <span>Nợ đơn: {money(o.debt)}{take > 0 && take < o.debt ? ` · còn ${money(o.debt - take)}` : ""}</span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div class="card pay-submit-bar">
                <button class={"btn primary block" + (!valid || busy ? " faded" : "")} disabled={busy}
                  onClick={() => (valid ? confirm() : toast(
                    selectedOrders.length === 0 ? "Chọn ít nhất một đơn"
                      : customerDebt <= 0 ? "Khách hiện không còn công nợ"
                      : overCustomerDebt ? "Số tiền vượt tổng nợ khách"
                      : overSelectedDebt ? "Số tiền vượt nợ của các đơn đã chọn"
                      : "Nhập số tiền",
                    "err",
                  ))}>
                  {busy ? "Đang thu…" : `Thu ${amount > 0 ? money(amount) : ""} (${method === "Cash" ? "TM" : "CK"})`}
                </button>
              </div>
            </>
          ) : (
            <div class="card muted small">
              Mọi đơn đang nợ của khách đã bị <b>ẩn khỏi trang thu tiền</b>. Đưa lại đơn bên dưới để thu.
            </div>
          )}

          {hiddenOrders.length > 0 && (
            <div class="card">
              <button class="pay-hidden-head" onClick={() => setHiddenOpen((s) => !s)}>
                <Icon name="ban" size={15} /> Đã ẩn khỏi trang thu tiền ({hiddenOrders.length})
                <Icon name="chevronDown" size={14} class={"pay-hidden-chev" + (hiddenOpen ? " flip" : "")} />
              </button>
              {hiddenOpen && (
                <ul class="pay-alloc-list">
                  {hiddenOrders.map((o) => (
                    <li class="pay-alloc" key={o.thread_id}>
                      <div class="pay-order-row">
                        {orderLink(o)}
                        <button class="btn small ghost pay-unhide" disabled={togglingId === o.thread_id}
                          onClick={() => toggleHide(o.thread_id, false)}>
                          <Icon name="refresh" size={14} /> Đưa lại
                        </button>
                      </div>
                      <div class="row space muted small">
                        <span>{o.created ? <>{fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : ""}</span>
                        <span>Nợ đơn: {money(o.total)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
