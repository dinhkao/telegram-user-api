// Bảng ĐƠN + LÃI phân trang cho dashboard lợi nhuận (#/loi-nhuan, tab Đơn hàng).
// Nguồn: GET /api/profit/orders (profit_dashboard/queries.orders_feed). Chạm 1
// dòng → bung chi tiết từng SP (giá bán/vốn/lãi) + phí. Lọc theo SP/khách do
// trang cha truyền (mở từ trang chi tiết SP/khách nếu cần).
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtQty } from "../format";
import { LoadingInline, ErrorState, EmptyState } from "../ui/states";
import type { DateRange } from "./ProfitDateBar";

type FeedItem = {
  code: string; qty: number; sell_price: number; cost_price: number;
  revenue: number; cost: number; profit: number; has_cost: boolean;
};
type FeedOrder = {
  thread_id: number; customer: string; date: string; revenue: number;
  cost: number; profit: number; has_cost: boolean; items: FeedItem[];
  fees: { vat: number; pvc: number; discount: number; fee_total: number };
  order_text: string;
};

export function ProfitOrdersFeed({ range }: { range: DateRange }) {
  const [orders, setOrders] = useState<FeedOrder[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const load = (p: number, reset: boolean) => {
    setBusy(true);
    setErr("");
    getJSON(`/api/profit/orders?since=${range.since}&until=${range.until}&page=${p}&per_page=50`, { cache: false })
      .then((j) => {
        setOrders((prev) => (reset ? j.orders : [...prev, ...j.orders]));
        setHasMore(!!j.has_more);
        setTotal(j.total || 0);
        setPage(p);
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải"))
      .finally(() => setBusy(false));
  };
  useEffect(() => { load(1, true); }, [range.since, range.until]);

  if (err && !orders.length) return <ErrorState msg={err} onRetry={() => load(1, true)} />;
  return (
    <div class="card">
      <div class="ie-head">Đơn hàng <span class="ie-count">{total} đơn</span></div>
      {!orders.length && !busy ? <EmptyState>Không có đơn trong khoảng ngày này.</EmptyState> : (
        <table class="inv-mini pf-table">
          <thead><tr><th>Đơn / khách</th><th class="num">DT</th><th class="num">Lãi</th></tr></thead>
          <tbody>
            {orders.map((o) => (
              <>
                <tr key={o.thread_id} onClick={() => setOpen(open === o.thread_id ? null : o.thread_id)}>
                  <td>
                    <a href={`#/order/${o.thread_id}`} onClick={(e) => e.stopPropagation()}>#{o.thread_id}</a>
                    {" "}<span class="muted small">{o.date}</span><br />
                    <a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}`}
                      onClick={(e) => e.stopPropagation()}>{o.customer || "Khách lẻ"}</a>
                  </td>
                  <td class="num">{money(o.revenue)}</td>
                  <td class="num">{o.has_cost
                    ? <b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}</b>
                    : <span class="t-warn small">chưa có vốn</span>}</td>
                </tr>
                {open === o.thread_id && (
                  <tr class="pf-expand"><td colSpan={3}>
                    <table class="inv-mini">
                      <thead><tr><th>SP</th><th class="num">SL</th><th class="num">Bán</th><th class="num">Vốn</th><th class="num">Lãi</th></tr></thead>
                      <tbody>
                        {o.items.map((it, i) => (
                          <tr key={i}>
                            <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(it.code)}`}>{it.code}</a></td>
                            <td class="num">{fmtQty(it.qty)}</td>
                            <td class="num">{money(it.sell_price)}</td>
                            <td class="num">{it.has_cost ? money(it.cost_price) : <span class="t-warn">—</span>}</td>
                            <td class="num">{it.has_cost ? money(it.profit) : "—"}</td>
                          </tr>
                        ))}
                        {(o.fees?.fee_total || 0) !== 0 && (
                          <tr class="sub"><td colSpan={4} class="lbl">
                            Phí (VAT {money(o.fees.vat)} + PVC {money(o.fees.pvc)} − CK {money(o.fees.discount)})
                          </td><td class="num">{money(o.fees.fee_total)}</td></tr>
                        )}
                      </tbody>
                    </table>
                  </td></tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
      {busy && <LoadingInline />}
      {hasMore && !busy && (
        <button class="btn block mt-2" onClick={() => load(page + 1, false)}>Tải thêm…</button>
      )}
    </div>
  );
}
