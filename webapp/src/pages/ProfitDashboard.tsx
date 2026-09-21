// Tổng quan lợi nhuận: kỳ báo cáo, bộ lọc nghiệp vụ, cảnh báo và drill-down.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, postJSON, isOffice } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar } from "../detail/ProfitDateBar";
import { presetRange, validRange, displayRange, type DateRange } from "../detail/profitDates";
import { DEFAULT_FILTERS, PAYMENT_OPTIONS, PROFIT_OPTIONS, COST_OPTIONS, QUICK_FILTERS, profitParams, type ProfitFilters } from "../detail/profitFilters";
import { ProfitOrdersFeed } from "../detail/ProfitOrdersFeed";
import { ProfitSummary, ProfitOverview, ProfitCoverageNote } from "../detail/ProfitOverview";
import { ProfitChart } from "../detail/ProfitChart";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

// Tab Sản phẩm: bảng lãi theo SP + Ô GIÁ VỐN MỚI sửa hàng loạt → POST /api/profit/costs
function ProductCostTable({ products, range, onSaved }: { products: any[]; range: DateRange; onSaved: () => void }) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [onlyMissing, setOnlyMissing] = useState(false);   // "Chọn SP chưa có giá vốn" bản gốc
  const missing = products.filter((p) => p.missing_cost_lines > 0).length;
  const shown = onlyMissing ? products.filter((p) => p.missing_cost_lines > 0) : products;
  const dirty = Object.entries(edits).filter(([, v]) => v.trim() !== "");
  const save = async () => {
    const updates: Record<string, number> = {};
    for (const [code, v] of dirty) {
      const digits = v.replace(/[.,\s]/g, "");
      const n = Number(digits);
      if (!/^\d+$/.test(digits) || !Number.isSafeInteger(n)) { toast(`Giá vốn ${code} phải là số nguyên không âm`, "err"); return; }
      updates[code] = n;
    }
    if (!Object.keys(updates).length) { toast("Chưa nhập giá vốn mới nào", "info"); return; }
    setBusy(true);
    try {
      await postJSON("/api/profit/costs", { updates });
      toast(`Đã lưu giá vốn ${Object.keys(updates).length} SP`, "ok");
      setEdits({});
      onSaved();
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };
  return (
    <div class="card">
      <div class="row space">
        <div class="ie-head">Lợi nhuận theo SP <span class="ie-count">{shown.length} mã</span></div>
        <button class="btn small primary" disabled={busy || !dirty.length} onClick={save}>
          <Icon name="save" size={14} /> Lưu giá vốn{dirty.length ? ` (${dirty.length})` : ""}
        </button>
      </div>
      {missing > 0 && (
        <div class="chips">
          <button class={"chip" + (onlyMissing ? " active" : "")} onClick={() => setOnlyMissing((v) => !v)}>
            ⚠ Thiếu giá vốn trong đơn ({missing})
          </button>
        </div>
      )}
      <p class="small muted">Giá vốn đã dự tính VAT bán ra. Lãi SP chưa cộng VAT và phí cấp đơn; xem tổng đơn để có đủ các khoản này. Giá vốn mới không thay giá đã lưu trong đơn. * Lãi chưa đầy đủ do có dòng thiếu vốn.</p>
      {!shown.length && <EmptyState>Không có sản phẩm phù hợp.</EmptyState>}
      <div class="pf-table-scroll"><table class="inv-mini pf-table pf-products-table">
        <thead><tr><th>SP</th><th class="num">Vốn hiện tại</th><th class="num">Vốn mới</th><th class="num">SL / đơn</th><th class="num">Doanh thu</th><th class="num">Tổng vốn</th><th class="num">Lãi / biên</th></tr></thead>
        <tbody>
          {shown.map((p) => (
            <tr key={p.code}>
              <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}?${new URLSearchParams(range)}`} title={p.name}>{p.code}</a><div class="small muted">{p.name}</div>{p.missing_cost_lines > 0 && <span class="small t-warn">{p.missing_cost_lines} dòng thiếu vốn</span>}</td>
              <td class="num">{p.cost_price ? money(p.cost_price) : <span class="t-warn">chưa có</span>}</td>
              <td class="num"><input class="pf-cost-inp" inputMode="numeric" placeholder="giá"
                aria-label={`Giá vốn mới ${p.code}`} value={edits[p.code] ?? ""}
                onInput={(e: any) => setEdits((prev) => ({ ...prev, [p.code]: e.target.value }))} /></td>
              <td class="num">{fmtQty(p.qty)}<div class="small muted">{p.orders} đơn</div></td><td class="num">{money(p.revenue)}</td><td class="num">{money(p.cost)}</td>
              <td class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}{p.missing_cost_lines > 0 ? " *" : ""}</b><div class="small muted">{p.margin == null ? "—" : `${p.margin}%`}</div></td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </div>
  );
}

function initialState(): { range: DateRange; filters: ProfitFilters } {
  const fallback = { range: presetRange("today"), filters: { ...DEFAULT_FILTERS, payment: sessionStorage.getItem("pf_paid") === "1" ? "received" : "all" } };
  try {
    const saved = JSON.parse(sessionStorage.getItem("pf_dashboard_v2") || "null");
    if (!saved || !validRange(saved.range)) return fallback;
    const f = saved.filters;
    if (typeof f?.product !== "string" || typeof f?.customer !== "string" || !PAYMENT_OPTIONS.some(([k]) => k === f.payment)
      || !PROFIT_OPTIONS.some(([k]) => k === f.profitability) || !COST_OPTIONS.some(([k]) => k === f.cost_status)) return fallback;
    return saved;
  } catch { return fallback; }
}

export function ProfitDashboard() {
  const [initial] = useState(initialState);
  const [range, setRange] = useState(initial.range);
  const [filters, setFilters] = useState<ProfitFilters>(initial.filters);
  const [applied, setApplied] = useState(filters);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState(() => {
    const stored = sessionStorage.getItem("pf_tab") || "overview";
    return ["overview", "don", "sp", "chart"].includes(stored) ? stored : "overview";
  });
  const [sort, setSort] = useState("newest");
  const requestId = useRef(0);
  const office = isOffice();
  const pickTab = (t: string) => { setTab(t); sessionStorage.setItem("pf_tab", t); };
  useEffect(() => {
    const timer = window.setTimeout(() => setApplied(filters), filters.product !== applied.product || filters.customer !== applied.customer ? 300 : 0);
    return () => clearTimeout(timer);
  }, [filters]);
  useEffect(() => { sessionStorage.setItem("pf_dashboard_v2", JSON.stringify({ range, filters })); }, [range, filters]);
  useEffect(() => {
    const id = ++requestId.current;
    if (!office) { setLoading(false); return; }
    setLoading(true); setErr(""); setData(null);
    getJSON(`/api/profit/dashboard?${profitParams(range, applied)}`, { cache: false })
      .then(d => { if (id === requestId.current) setData(d); })
      .catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Lỗi tải"); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { requestId.current++; };
  }, [range.since, range.until, applied, reload, office]);
  const refresh = () => setReload(v => v + 1);
  const freeze = async () => {
    if (!(await confirmDialog("Ghi vốn hiện tại làm ƯỚC TÍNH vào đơn từ mốc 460000 còn thiếu? Áp dụng ngoài bộ lọc đang xem. Báo cáo vẫn yêu cầu vốn lịch sử được xác nhận; giá ước tính không làm đơn thành đủ vốn.", { okLabel: "Đóng băng" }))) return;
    setBusy(true);
    try { const j = await postJSON("/api/profit/freeze-costs", {}); toast(`Đã ghi vốn ước tính vào ${j.updated} đơn`, "ok"); refresh(); }
    catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };
  const set = (key: keyof ProfitFilters, value: string) => setFilters(f => ({ ...f, [key]: value }));
  const quick = (patch: Partial<ProfitFilters>) => setFilters(f => ({ ...DEFAULT_FILTERS, product: f.product, customer: f.customer, ...patch }));
  const activeQuick = QUICK_FILTERS.find(q => ["payment", "profitability", "cost_status"].every(k => filters[k as keyof ProfitFilters] === ({ ...DEFAULT_FILTERS, ...q.filters })[k as keyof ProfitFilters]))?.id;
  const filterCount = Object.entries(filters).filter(([k, v]) => v !== DEFAULT_FILTERS[k as keyof ProfitFilters]).length;
  const pending = loading || filters !== applied;
  if (!office) return <div class="prod-detail"><PageHead fallback="#/home" title="Lợi nhuận" /><EmptyState>Chỉ văn phòng được xem trang lợi nhuận.</EmptyState></div>;
  return <div class="prod-detail pf-dashboard">
    <PageHead fallback="#/home" title="Lợi nhuận" sub="Theo dõi hiệu quả từng kỳ, tìm đơn cần xử lý"
      right={<a class="btn small" href="#/loi-nhuan/cai-dat" aria-label="Cài đặt lợi nhuận"><Icon name="settings" size={16} /></a>} />
    <ProfitDateBar range={range} onChange={setRange} />
    <div class="card pf-filters">
      <div class="pf-section-label">Bộ lọc nhanh <button class="pf-reset" disabled={!filterCount} onClick={() => setFilters({ ...DEFAULT_FILTERS })}>Xoá lọc{filterCount ? ` (${filterCount})` : ""}</button></div>
      <div class="chips pf-presets">{QUICK_FILTERS.map(q => <button class={"chip" + (activeQuick === q.id ? " active" : "")} aria-pressed={activeQuick === q.id} onClick={() => quick(q.filters)}>{q.label}</button>)}</div>
      <div class="pf-filter-inputs"><label>Mã sản phẩm<input class="note-inp" placeholder="Nhập chính xác mã SP" value={filters.product} onInput={(e: any) => set("product", e.currentTarget.value)} /></label>
        <label>Khách hàng<input class="note-inp" placeholder="Tìm theo tên khách" value={filters.customer} onInput={(e: any) => set("customer", e.currentTarget.value)} /></label></div>
      <details class="pf-advanced"><summary>Kết hợp bộ lọc chi tiết</summary><div class="pf-filter-selects">
        {([["payment", "Phiếu thu", PAYMENT_OPTIONS], ["profitability", "Mức lợi nhuận", PROFIT_OPTIONS], ["cost_status", "Giá vốn", COST_OPTIONS]] as const).map(([key, label, options]) =>
          <label>{label}<select aria-label={label} value={filters[key]} onChange={(e: any) => set(key, e.currentTarget.value)}>{options.map(([v, l]) => <option value={v}>{l}</option>)}</select></label>)}
      </div></details>
      <div class="pf-filter-context" aria-live="polite">{[...PAYMENT_OPTIONS, ...PROFIT_OPTIONS, ...COST_OPTIONS].filter(([key]) => key !== "all" && [filters.payment, filters.profitability, filters.cost_status].includes(key)).map(([, label]) => <span>{label}</span>)}</div>
      <p class="small muted">Lọc theo toàn đơn hàng. “Có phiếu thu” bao gồm cả đơn thu một phần. Bộ lọc mức lãi chỉ xét đơn đủ giá vốn.</p>
    </div>
    <div class="pf-report-toolbar"><span>{pending ? "Đang cập nhật…" : `${data?.summary.orders || 0} đơn bán · ${data?.summary.returns || 0} phiếu trả · ${displayRange(range)}`}</span>
      <button class="btn small" disabled={pending} onClick={refresh}>Làm mới</button></div>
    {pending ? <Loading label="Đang tính báo cáo theo bộ lọc…" /> : err ? <ErrorState msg={err} onRetry={refresh} /> : data && <>
      <ProfitSummary s={data.summary} /><ProfitCoverageNote coverage={data.coverage} />
      {!data.summary.entries && <div class="card"><EmptyState>Không có đơn phù hợp. Hãy mở rộng khoảng ngày hoặc xoá bớt bộ lọc.</EmptyState></div>}
      <div class="seg pf-tabs">{[["overview", "Tổng quan"], ["don", "Đơn hàng"], ["sp", "Sản phẩm"], ["chart", "Xu hướng"]].map(([k, label]) =>
        <button class={"seg-btn" + (tab === k ? " active" : "")} aria-pressed={tab === k} onClick={() => pickTab(k)}>{label}</button>)}</div>
      {tab === "overview" && <ProfitOverview data={data} range={range} onFilter={patch => { setFilters(f => ({ ...f, ...patch })); pickTab("don"); }} />}
      {tab === "don" && <><label class="pf-sort">Sắp xếp đơn<select aria-label="Sắp xếp đơn" value={sort} onChange={(e: any) => setSort(e.currentTarget.value)}>
        {[["newest", "Mới nhất"], ["oldest", "Cũ nhất"], ["profit_desc", "Lãi cao nhất"], ["profit_asc", "Lãi thấp nhất"], ["revenue_desc", "Doanh thu cao nhất"], ["margin_asc", "Biên lãi thấp nhất"]].map(([v, label]) => <option value={v}>{label}</option>)}
      </select></label><ProfitOrdersFeed key={`${profitParams(range, applied)}:${sort}:${reload}`} range={range} product={applied.product} customer={applied.customer}
        payment={applied.payment} profitability={applied.profitability} costStatus={applied.cost_status} sort={sort} /></>}
      {tab === "sp" && <ProductCostTable products={data.products || []} range={range} onSaved={refresh} />}
      {tab === "chart" && <ProfitChart chart={data.chart || []} />}
    </>}
    <div class="pf-admin-actions"><a class="btn small" href={`#/loi-nhuan/khach?${new URLSearchParams(range)}`}><Icon name="users" size={14} /> Khách hàng</a>
      <button class="btn small" disabled={busy} onClick={freeze}>Ước tính vốn đơn thiếu</button></div>
  </div>;
}
