// Bảng ĐƠN + LÃI phân trang cho dashboard lợi nhuận (#/loi-nhuan, tab Đơn hàng).
// Nguồn: GET /api/profit/orders (profit_dashboard/queries.orders_feed). Mỗi dòng
// hiện CHIP SP (mã ×SL, vàng = chưa có giá vốn — như bản legacy) + biên LN;
// chạm dòng → bung chi tiết từng SP (giá bán/vốn/lãi) + phí. Lọc SP/khách do
// trang cha truyền (ô lọc trên dashboard).
import { useEffect, useRef, useState } from "preact/hooks";
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
  cost: number; profit: number; has_cost: boolean; has_payment?: boolean;
  items: FeedItem[];
  fees: { vat: number; pvc: number; discount: number; fee_total: number };
  order_text: string;
};

export function ProfitOrdersFeed({ range, product, customer, paidOnly }: {
  range: DateRange; product?: string; customer?: string; paidOnly?: boolean;
}) {
  const [orders, setOrders] = useState<FeedOrder[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const qs = () => {
    const p = new URLSearchParams({ since: range.since, until: range.until, per_page: "50" });
    if (product?.trim()) p.set("product", product.trim());
    if (customer?.trim()) p.set("customer", customer.trim());
    if (paidOnly) p.set("paid", "1");
    return p;
  };
  const load = (p: number, reset: boolean) => {
    setBusy(true);
    setErr("");
    const params = qs();
    params.set("page", String(p));
    getJSON(`/api/profit/orders?${params}`, { cache: false })
      .then((j) => {
        setOrders((prev) => (reset ? j.orders : [...prev, ...j.orders]));
        setHasMore(!!j.has_more);
        setTotal(j.total || 0);
        setPage(p);
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải"))
      .finally(() => setBusy(false));
  };
  useEffect(() => { load(1, true); }, [range.since, range.until, product, customer, paidOnly]);

  // Sentinel TỰ TẢI trang kế khi cuộn tới đáy (nút "Tải thêm" giữ làm dự phòng).
  // Cần cho cả hệ nhớ-vị-trí-cuộn: BACK về giữa danh sách dài → vòng khôi phục
  // cuộn xuống làm lộ sentinel → tự tải tiếp → về đúng chỗ cũ.
  const sentinel = useRef<HTMLDivElement>(null);
  const st = useRef({ busy, hasMore, page, load });
  st.current = { busy, hasMore, page, load };
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        const s = st.current;
        if (!s.busy && s.hasMore) s.load(s.page + 1, false);
      }
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  if (err && !orders.length) return <ErrorState msg={err} onRetry={() => load(1, true)} />;
  return (
    <div class="card">
      <div class="ie-head">Đơn hàng <span class="ie-count">{total} đơn</span></div>
      {!orders.length && !busy ? <EmptyState>Không có đơn trong khoảng ngày này.</EmptyState> : (
        <table class="inv-mini pf-table">
          <thead><tr><th>Đơn / khách / SP</th><th class="num">DT</th><th class="num">Lãi · biên</th></tr></thead>
          <tbody>
            {orders.map((o) => (
              <>
                <tr key={o.thread_id} onClick={() => setOpen(open === o.thread_id ? null : o.thread_id)}>
                  <td>
                    <a href={`#/order/${o.thread_id}`} onClick={(e) => e.stopPropagation()}>#{o.thread_id}</a>
                    {" "}<span class="muted small">{o.date}</span><br />
                    <a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}`}
                      onClick={(e) => e.stopPropagation()}>{o.customer || "Khách lẻ"}</a>
                    {o.has_payment === false && <span class="t-warn small"> · chưa TT</span>}
                    {/* chip SP như bản gốc: mã ×SL, vàng = chưa có giá vốn */}
                    <span class="pf-prod-chips">
                      {o.items.slice(0, 5).map((it) => (
                        <span key={it.code} class={"pf-prod-chip" + (it.has_cost ? "" : " warn")}>
                          {it.code}<span class="q">×{fmtQty(it.qty)}</span>
                        </span>
                      ))}
                      {o.items.length > 5 && <span class="pf-prod-chip">+{o.items.length - 5}</span>}
                    </span>
                  </td>
                  <td class="num">{money(o.revenue)}</td>
                  <td class="num">{o.has_cost
                    ? <><b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}</b>
                        <div class="muted small">{o.revenue > 0 ? `${((o.profit / o.revenue) * 100).toFixed(1)}%` : ""}</div></>
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
                        <tr class="sub"><td colSpan={4} class="lbl">Giá vốn đơn</td><td class="num">{money(o.cost)}</td></tr>
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
      <div ref={sentinel} style="height:1px" />
      {hasMore && !busy && (
        <button class="btn block mt-2" onClick={() => load(page + 1, false)}>Tải thêm…</button>
      )}
    </div>
  );
}
