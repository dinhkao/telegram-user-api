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
  code: string; qty: number; sell_price: number; cost_price: number | null;
  revenue: number; cost: number; profit: number | null; has_cost: boolean;
};
type FeedOrder = {
  kind?: string; return_id?: number; customer_total?: number; thread_id: number; customer: string; date: string; revenue: number;
  cost: number; profit: number; has_cost: boolean; has_payment?: boolean; cost_complete?: boolean;
  items: FeedItem[];
  fees: { vat: number; pvc: number; discount: number; fee_total: number; shipping_cost?: number };
  order_text: string;
};

export function ProfitOrdersFeed({ range, product, customer, paidOnly, payment = "all", profitability = "all", costStatus = "all", sort = "newest" }: {
  range: DateRange; product?: string; customer?: string; paidOnly?: boolean;
  payment?: string; profitability?: string; costStatus?: string; sort?: string;
}) {
  const [orders, setOrders] = useState<FeedOrder[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const requestId = useRef(0);
  const inFlight = useRef(false);
  const qs = () => {
    const p = new URLSearchParams({ since: range.since, until: range.until, per_page: "50" });
    if (product?.trim()) p.set("product", product.trim());
    if (customer?.trim()) p.set("customer", customer.trim());
    if (paidOnly) p.set("paid", "1");
    p.set("payment", payment); p.set("profitability", profitability); p.set("cost_status", costStatus); p.set("sort", sort);
    return p;
  };
  const load = (p: number, reset: boolean) => {
    if (inFlight.current && !reset) return;
    const id = ++requestId.current;
    inFlight.current = true;
    if (reset) { setOrders([]); setTotal(0); setHasMore(false); setOpen(null); }
    setBusy(true);
    setErr("");
    const params = qs();
    params.set("page", String(p));
    getJSON(`/api/profit/orders?${params}`, { cache: false })
      .then((j) => {
        if (id !== requestId.current) return;
        setOrders((prev) => (reset ? j.orders : [...prev, ...j.orders]));
        setHasMore(!!j.has_more);
        setTotal(j.total || 0);
        setPage(p);
      })
      .catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Lỗi tải"); })
      .finally(() => { if (id === requestId.current) { setBusy(false); inFlight.current = false; } });
  };
  useEffect(() => { load(1, true); return () => { requestId.current++; }; }, [range.since, range.until, product, customer, paidOnly, payment, profitability, costStatus, sort]);

  // Sentinel TỰ TẢI trang kế khi cuộn tới đáy (nút "Tải thêm" giữ làm dự phòng).
  // Cần cho cả hệ nhớ-vị-trí-cuộn: BACK về giữa danh sách dài → vòng khôi phục
  // cuộn xuống làm lộ sentinel → tự tải tiếp → về đúng chỗ cũ.
  const sentinel = useRef<HTMLDivElement>(null);
  const st = useRef({ busy, hasMore, page, load, err });
  st.current = { busy, hasMore, page, load, err };
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) {
        const s = st.current;
        if (!s.busy && !s.err && s.hasMore) s.load(s.page + 1, false);
      }
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div class="card">
      <div class="ie-head">Đơn bán & phiếu trả <span class="ie-count">{total} giao dịch</span></div>
      {err && <ErrorState msg={err} onRetry={() => load(orders.length ? page + 1 : 1, !orders.length)} />}
      {!orders.length && !busy && !err ? <EmptyState>Không có đơn trong khoảng ngày này.</EmptyState> : (
        <div class="pf-table-scroll"><table class="inv-mini pf-table">
          <thead><tr><th>Đơn / khách / SP</th><th class="num">Doanh thu</th><th class="num">Lãi · biên</th></tr></thead>
          <tbody>
            {orders.map((o) => (
              <>
                <tr key={o.thread_id} onClick={() => setOpen(open === o.thread_id ? null : o.thread_id)}>
                  <td>
                    <button class="pf-expand-toggle" aria-label={`Chi tiết đơn ${o.thread_id}`} aria-expanded={open === o.thread_id} onClick={e => { e.stopPropagation(); setOpen(open === o.thread_id ? null : o.thread_id); }}>{open === o.thread_id ? "−" : "+"}</button>{" "}
                    <a href={o.kind === "return" ? `#/tra-hang/${o.return_id}` : `#/order/${o.thread_id}`} onClick={(e) => e.stopPropagation()}>{o.kind === "return" ? `Trả #${o.return_id}` : `#${o.thread_id}`}</a>
                    {" "}<span class="muted small">{o.date}</span><br />
                    <a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}?${new URLSearchParams(range)}`}
                      onClick={(e) => e.stopPropagation()}>{o.customer || "Khách lẻ"}</a>
                    {o.kind !== "return" && <span class={"small " + (o.has_payment ? "muted" : "t-warn")}> · {o.has_payment ? "có phiếu thu" : "chưa có phiếu thu"}</span>}
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
                  <td class="num">{(o.has_cost || o.kind === "return")
                    ? <><b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}{o.cost_complete === false ? " *" : ""}</b>
                        <div class="muted small">{o.cost_complete && o.revenue > 0 ? `${((o.profit / o.revenue) * 100).toFixed(1)}%` : ""}</div></>
                    : <span class="t-warn small">chưa có vốn</span>}{o.cost_complete === false && o.has_cost && <div class="small t-warn">chỉ phần lãi đã xác định</div>}</td>
                </tr>
                {open === o.thread_id && (
                  <tr class="pf-expand"><td colSpan={3}>
                    <table class="inv-mini">
                      <thead><tr><th>SP</th><th class="num">SL</th><th class="num">Bán</th><th class="num">Vốn</th><th class="num">Lãi dòng*</th></tr></thead>
                      <tbody>
                        {o.items.map((it, i) => (
                          <tr key={i}>
                            <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(it.code)}?${new URLSearchParams(range)}`}>{it.code}</a></td>
                            <td class="num">{fmtQty(it.qty)}</td>
                            <td class="num">{money(it.sell_price)}</td>
                            <td class="num">{it.has_cost ? it.cost_price == null ? "—" : money(it.cost_price) : <span class="t-warn">—</span>}</td>
                            <td class="num">{it.has_cost ? money(it.profit ?? 0) : "—"}</td>
                          </tr>
                        ))}
                        <tr><td colSpan={5} class="small muted">* Lãi dòng chưa cộng VAT và điều chỉnh cấp đơn bên dưới. Giá vốn đã dự tính VAT bán ra.</td></tr>
                        <tr class="sub"><td colSpan={4} class="lbl">VAT thu khách (giá vốn đã dự tính VAT)</td><td class="num">{money(o.fees?.vat)}</td></tr>
                        <tr class="sub"><td colSpan={4} class="lbl">Điều chỉnh cấp đơn: VAT + phí thu khách − chiết khấu − chi phí giao hàng</td><td class="num">{money((o.fees?.fee_total || 0) - (o.fees?.shipping_cost || 0))}</td></tr>
                        <tr class="sub"><td colSpan={4} class="lbl">Tổng tiền khách thanh toán (gồm VAT)</td><td class="num">{money(o.customer_total ?? 0)}</td></tr>
                        {o.kind === "return" && <tr><td colSpan={5} class="small muted">Số âm là giảm doanh thu. Giá vốn âm là phần hoàn vốn khi nhập kho; hàng hủy không hoàn vốn.</td></tr>}
                        <tr class="sub"><td colSpan={4} class="lbl">{o.kind === "return" ? "Điều chỉnh giá vốn" : "Giá vốn đã xác định"}</td><td class="num">{money(o.cost)}</td></tr>
                      </tbody>
                    </table>
                  </td></tr>
                )}
              </>
            ))}
          </tbody>
        </table></div>
      )}
      {busy && <LoadingInline />}
      <div ref={sentinel} style="height:1px" />
      {hasMore && !busy && (
        <button class="btn block mt-2" onClick={() => load(page + 1, false)}>Tải thêm…</button>
      )}
    </div>
  );
}
