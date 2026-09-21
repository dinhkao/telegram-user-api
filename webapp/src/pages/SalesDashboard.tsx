// Báo cáo bán hàng: snapshot hôm nay/tuần/tháng + kỳ tùy chọn, xu hướng và top.
// Data: GET /api/sales-dashboard?since=&until= (office-only).
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, isOffice } from "../api";
import { money } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, Loading } from "../ui/states";
import {
  SALES_FILTER_CACHE_KEY, addDays, presetRange, readSalesFilter, salesFilterHash,
  startOfWeek, todayVN, type SalesFilterState, type SalesPresetKey, type SalesRange,
} from "../detail/salesFilterState";

type Range = SalesRange;
type Summary = {
  net_qty: number; gross_qty: number; return_qty: number;
  revenue: number; gross_revenue: number; return_revenue: number;
  orders: number; returns: number; customers: number; products: number;
  avg_order_value: number;
};
type Period = Range & {
  previous_since: string; previous_until: string;
  summary: Summary; previous: Summary;
  changes: Record<string, number | null>;
};
type Daily = Summary & { day: string };
type ProductRow = { code: string; name: string; net_qty: number; gross_qty: number; return_qty: number; revenue: number; orders: number; customers: number };
type CustomerRow = { name: string; net_qty: number; gross_qty: number; return_qty: number; revenue: number; orders: number; products: number };
type SalesData = {
  today: string;
  headline: { today: Period; week: Period; month: Period };
  selected: Period & {
    daily: Daily[]; chart_since: string; chart_until: string; chart_selected_day: string | null;
    top_products: ProductRow[]; top_customers: CustomerRow[];
  };
  coverage: any;
  _stale?: boolean;
};

type PresetKey = SalesPresetKey;
const dateShort = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}`;
const dateLong = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
const rangeLabel = (r: Range) => r.since === r.until ? dateLong(r.since) : `${dateLong(r.since)} – ${dateLong(r.until)}`;
const compactMoney = (v: number) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(v);
const qtyVN = (v: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(v);

function Change({ value, label = "so với kỳ trước" }: { value: number | null | undefined; label?: string }) {
  const cls = value == null || value === 0 ? "flat" : value > 0 ? "up" : "down";
  const text = value == null ? "Kỳ trước chưa có" : value === 0 ? "Không đổi" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return <span class={`sd-change ${cls}`} title={label}>{value != null && value !== 0 && <span aria-hidden="true">{value > 0 ? "↗" : "↘"}</span>} {text}</span>;
}

function SnapshotCard({ name, note, period, active, onClick }: {
  name: string; note: string; period: Period; active: boolean; onClick: () => void;
}) {
  return <button type="button" class={`sd-snapshot${active ? " active" : ""}`} onClick={onClick} aria-pressed={active}>
    <span class="sd-snapshot-top"><b>{name}</b><span>{note}</span></span>
    <strong>{compactMoney(period.summary.revenue)}<small>đ</small></strong>
    <span class="sd-snapshot-meta"><span>{qtyVN(period.summary.net_qty)} SP</span><i /> <span>{period.summary.customers} khách</span></span>
    <Change value={period.changes.revenue} />
  </button>;
}

function MetricCard({ icon, label, value, sub, change, tone }: {
  icon: string; label: string; value: string; sub: string; change: number | null | undefined; tone: string;
}) {
  return <div class={`sd-metric ${tone}`}>
    <span class="sd-metric-icon"><Icon name={icon} size={17} /></span>
    <span class="sd-metric-label">{label}</span>
    <b>{value}</b>
    <span class="sd-metric-foot"><span>{sub}</span><Change value={change} /></span>
  </div>;
}

type ChartPoint = Daily & { key: string; label: string };
function chartPoints(daily: Daily[]): { points: ChartPoint[]; unit: string } {
  const unit = daily.length > 180 ? "month" : daily.length > 45 ? "week" : "day";
  const buckets = new Map<string, ChartPoint>();
  for (const row of daily) {
    const key = unit === "month" ? row.day.slice(0, 7) : unit === "week" ? startOfWeek(row.day) : row.day;
    let point = buckets.get(key);
    if (!point) {
      point = { ...row, key, label: unit === "month" ? `T${Number(key.slice(5, 7))}/${key.slice(2, 4)}` : unit === "week" ? `Tuần ${dateShort(key)}` : dateShort(key) };
      for (const k of ["net_qty", "gross_qty", "return_qty", "revenue", "gross_revenue", "return_revenue", "orders", "returns", "customers", "products", "avg_order_value"] as (keyof Summary)[]) (point as any)[k] = 0;
      buckets.set(key, point);
    }
    point.net_qty += row.net_qty; point.gross_qty += row.gross_qty; point.return_qty += row.return_qty;
    point.revenue += row.revenue; point.gross_revenue += row.gross_revenue; point.return_revenue += row.return_revenue;
    point.orders += row.orders; point.returns += row.returns;
  }
  return { points: [...buckets.values()], unit };
}

function SalesTrend({ daily, selectedDay }: { daily: Daily[]; selectedDay?: string | null }) {
  const { points, unit } = chartPoints(daily);
  const [selected, setSelected] = useState(selectedDay || "");
  useEffect(() => setSelected(selectedDay || ""), [selectedDay]);
  if (!points.length) return null;
  const chosen = points.find(p => p.key === selected) || points.find(p => p.key === selectedDay) || points[points.length - 1];
  const W = 600, H = 250, L = 48, R = 42, T = 25, B = 35;
  const plotW = W - L - R, plotH = H - T - B, step = plotW / Math.max(1, points.length);
  const revenues = points.map(p => p.revenue), quantities = points.map(p => p.net_qty);
  const revMax = Math.max(1, ...revenues), revMin = Math.min(0, ...revenues), revSpan = revMax - revMin;
  const qtyMax = Math.max(1, ...quantities), qtyMin = Math.min(0, ...quantities), qtySpan = qtyMax - qtyMin;
  const ry = (v: number) => T + (revMax - v) / revSpan * plotH;
  const qy = (v: number) => T + (qtyMax - v) / qtySpan * plotH;
  const x = (i: number) => L + (i + .5) * step;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${qy(p.net_qty)}`).join(" ");
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  return <section class="sd-panel sd-trend">
    <div class="sd-section-head"><div><span>{selectedDay ? "TUẦN CHỨA NGÀY ĐANG CHỌN" : "NHỊP BÁN"}</span><h3>Doanh thu & số lượng</h3></div><span class="sd-legend"><i class="bar" /> Doanh thu <i class="line" /> SL thuần</span></div>
    <div class="sd-chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} class="sd-chart" role="img" aria-label="Biểu đồ doanh thu dạng cột và số lượng bán thuần dạng đường">
        <defs><linearGradient id="sd-bars" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ef6c4d" /><stop offset="1" stop-color="#f4a56d" /></linearGradient></defs>
        {[0, .5, 1].map(t => <g key={t}><line x1={L} x2={W - R} y1={T + t * plotH} y2={T + t * plotH} class="sd-gridline" /><text x={L - 7} y={T + t * plotH + 4} text-anchor="end" class="sd-axis">{compactMoney(revMax - t * revSpan)}</text></g>)}
        <line x1={L} x2={W - R} y1={ry(0)} y2={ry(0)} class="sd-zero" />
        {points.map((p, i) => <g key={p.key} class={`${selected && selected !== p.key ? "dim" : ""}${chosen.key === p.key ? " active" : ""}`.trim()}>
          <rect x={x(i) - step * .31} width={Math.max(2, step * .62)} y={Math.min(ry(0), ry(p.revenue))} height={Math.max(1, Math.abs(ry(p.revenue) - ry(0)))} rx={Math.min(5, step * .16)} fill="url(#sd-bars)" />
          <rect class="sd-hit" x={L + i * step} y={T} width={step} height={plotH} onClick={() => setSelected(p.key)}><title>{p.label}: {money(p.revenue)}đ · {qtyVN(p.net_qty)} SP</title></rect>
          {i % labelEvery === 0 && <text x={x(i)} y={H - 12} text-anchor="middle" class="sd-axis">{p.label.replace("Tuần ", "")}</text>}
        </g>)}
        <path d={path} class="sd-qty-line" />
        {points.map((p, i) => <circle key={p.key} cx={x(i)} cy={qy(p.net_qty)} r={chosen.key === p.key ? 4 : 2.5} class="sd-qty-dot" />)}
        <text x={W - R + 7} y={T + 4} class="sd-axis sd-axis-qty">{qtyVN(qtyMax)}</text><text x={W - R + 7} y={T + plotH + 4} class="sd-axis sd-axis-qty">{qtyVN(qtyMin)}</text>
      </svg>
    </div>
    <div class="sd-chart-readout" aria-live="polite"><div><span>{unit === "day" ? dateLong(chosen.day) : chosen.label}</span><b>{money(chosen.revenue)}đ</b></div><div><span>Số lượng thuần</span><b>{qtyVN(chosen.net_qty)} SP</b></div><div><span>Đơn bán</span><b>{chosen.orders}</b></div></div>
  </section>;
}

function Ranking({ period }: { period: SalesData["selected"] }) {
  const [tab, setTab] = useState<"products" | "customers">("products");
  const [sort, setSort] = useState<"revenue" | "qty">("revenue");
  const source = tab === "products" ? period.top_products : period.top_customers;
  const rows = [...source].sort((a: any, b: any) => sort === "revenue" ? b.revenue - a.revenue : b.net_qty - a.net_qty).slice(0, 8);
  const max = Math.max(1, ...rows.map((row: any) => sort === "revenue" ? Math.max(0, row.revenue) : Math.max(0, row.net_qty)));
  const drill = (row: any) => tab === "products" ? `#/loi-nhuan/sp/${encodeURIComponent(row.code)}?since=${period.since}&until=${period.until}` : `#/loi-nhuan/khach/${encodeURIComponent(row.name)}?since=${period.since}&until=${period.until}`;
  return <section class="sd-panel sd-ranking">
    <div class="sd-section-head"><div><span>DẪN ĐẦU</span><h3>{tab === "products" ? "Sản phẩm bán chạy" : "Khách hàng nổi bật"}</h3></div>
      <select aria-label="Sắp xếp bảng xếp hạng" value={sort} onChange={(e: any) => setSort(e.currentTarget.value)}><option value="revenue">Theo doanh thu</option><option value="qty">Theo số lượng</option></select>
    </div>
    <div class="sd-rank-tabs" role="tablist"><button type="button" role="tab" aria-selected={tab === "products"} class={tab === "products" ? "active" : ""} onClick={() => setTab("products")}>Sản phẩm <b>{period.summary.products}</b></button><button type="button" role="tab" aria-selected={tab === "customers"} class={tab === "customers" ? "active" : ""} onClick={() => setTab("customers")}>Khách hàng <b>{period.summary.customers}</b></button></div>
    {!rows.length ? <EmptyState>Chưa có dữ liệu xếp hạng trong kỳ này.</EmptyState> : <div class="sd-rank-list">{rows.map((row: any, i) => {
      const value = sort === "revenue" ? row.revenue : row.net_qty;
      return <a href={drill(row)} class="sd-rank-row" key={tab === "products" ? row.code : row.name}>
        <span class="sd-rank-no">{String(i + 1).padStart(2, "0")}</span><span class="sd-rank-main"><b>{tab === "products" ? row.code : row.name}</b>{tab === "products" && row.name && <small>{row.name}</small>}<i style={{ width: `${Math.max(2, Math.max(0, value) / max * 100)}%` }} /></span>
        <span class="sd-rank-value"><b>{sort === "revenue" ? `${compactMoney(row.revenue)}đ` : `${qtyVN(row.net_qty)} SP`}</b><small>{sort === "revenue" ? `${qtyVN(row.net_qty)} SP thuần` : `${compactMoney(row.revenue)}đ`}</small>{row.return_qty > 0 && <em>Trả {qtyVN(row.return_qty)} SP</em>}</span><Icon name="chevronRight" size={15} />
      </a>;
    })}</div>}
  </section>;
}

function DataWarning({ coverage }: { coverage: any }) {
  if (!coverage?.quality_errors) return null;
  const count = ["invalid_orders", "undated_orders", "invalid_returns", "undated_returns", "return_amount_mismatches"].reduce((sum, key) => sum + Number(coverage[key] || 0), 0);
  return <div class="sd-warning" role="alert"><Icon name="info" size={17} /><span><b>Cần đối chiếu {count} mục dữ liệu.</b> Một số đơn hoặc phiếu trả lỗi/thiếu ngày chưa được tính đầy đủ.</span></div>;
}

export function SalesDashboard() {
  const office = isOffice();
  const [initial] = useState<SalesFilterState>(() => {
    let cached: string | null = null;
    try { cached = sessionStorage.getItem(SALES_FILTER_CACHE_KEY); } catch { /* ignore */ }
    return readSalesFilter(window.location.hash, cached, todayVN());
  });
  const [preset, setPreset] = useState<PresetKey>(initial.period);
  const [range, setRange] = useState<Range>(initial.range);
  const [draft, setDraft] = useState<Range>(range);
  const [showCustom, setShowCustom] = useState(false);
  const [data, setData] = useState<SalesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    if (!office) { setLoading(false); return; }
    const id = ++requestId.current;
    setLoading(true); setErr("");
    getJSON(`/api/sales-dashboard?since=${range.since}&until=${range.until}`, { cache: false })
      .then((result: SalesData) => { if (id === requestId.current) setData(result); })
      .catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Không tải được báo cáo bán hàng"); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { requestId.current++; };
  }, [range.since, range.until, reload, office]);

  const rememberFilter = (next: SalesFilterState) => {
    try { sessionStorage.setItem(SALES_FILTER_CACHE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    history.replaceState(null, "", salesFilterHash(next));
  };
  const pick = (key: Exclude<PresetKey, "custom">, serverToday = data?.today || todayVN()) => {
    const next = presetRange(key, serverToday);
    setPreset(key); setRange(next); setDraft(next); setShowCustom(false);
    rememberFilter({ period: key, range: next });
  };
  const applyCustom = () => {
    if (!draft.since || !draft.until || draft.since > draft.until) { setErr("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc."); return; }
    setPreset("custom"); setRange(draft); setShowCustom(false); setErr("");
    rememberFilter({ period: "custom", range: draft });
  };
  if (!office) return <div class="prod-detail sd-dashboard"><PageHead fallback="#/home" title="Báo cáo bán hàng" /><EmptyState>Chỉ văn phòng được xem doanh thu bán hàng.</EmptyState></div>;

  const selected = data?.selected;
  const headline = data?.headline;
  const selectedHasTransactions = !!selected && !!(selected.summary.orders || selected.summary.returns);
  const chartHasTransactions = !!selected?.daily.some(day => day.orders || day.returns);
  return <div class="prod-detail sd-dashboard">
    <PageHead fallback="#/home" title="Báo cáo bán hàng" sub="Số lượng · doanh thu · khách hàng"
      right={<button type="button" class="sd-refresh" onClick={() => setReload(v => v + 1)} disabled={loading} aria-label="Làm mới báo cáo"><Icon name="refresh" size={17} /></button>} />

    {headline && <div class="sd-snapshots" aria-label="Tổng quan nhanh theo kỳ">
      <SnapshotCard name="Hôm nay" note={dateShort(headline.today.until)} period={headline.today} active={preset === "today"} onClick={() => pick("today")} />
      <SnapshotCard name="Tuần này" note={`${dateShort(headline.week.since)}–${dateShort(headline.week.until)}`} period={headline.week} active={preset === "week"} onClick={() => pick("week")} />
      <SnapshotCard name="Tháng này" note={`T${Number(headline.month.until.slice(5, 7))}`} period={headline.month} active={preset === "month"} onClick={() => pick("month")} />
    </div>}

    <div class="sd-periods"><span>Xem kỳ</span>{([ ["today", "Ngày"], ["week", "Tuần"], ["month", "Tháng"], ["30days", "30 ngày"], ["quarter", "Quý"], ["year", "Năm"] ] as [PresetKey, string][]).map(([key, label]) => <button type="button" class={preset === key ? "active" : ""} aria-pressed={preset === key} onClick={() => pick(key)}>{label}</button>)}<button type="button" class={preset === "custom" ? "active" : ""} aria-expanded={showCustom} onClick={() => setShowCustom(v => !v)}><Icon name="calendar" size={14} /> Khác</button></div>
    {showCustom && <div class="sd-custom"><label>Từ ngày<input type="date" value={draft.since} onInput={(e: any) => setDraft(v => ({ ...v, since: e.currentTarget.value }))} /></label><label>Đến ngày<input type="date" value={draft.until} onInput={(e: any) => setDraft(v => ({ ...v, until: e.currentTarget.value }))} /></label><button type="button" onClick={applyCustom}>Xem báo cáo</button></div>}

    {loading ? <Loading label="Đang tổng hợp số bán, doanh thu và khách hàng…" /> : err ? <ErrorState msg={err} onRetry={() => setReload(v => v + 1)} /> : selected && <>
      <section class="sd-hero">
        <div class="sd-hero-kicker"><span>KỲ ĐANG XEM</span><b>{rangeLabel(selected)}</b></div>
        <div class="sd-hero-main"><span>Doanh thu thuần</span><strong>{money(selected.summary.revenue)}<small>đ</small></strong><Change value={selected.changes.revenue} label={`so với ${rangeLabel({ since: selected.previous_since, until: selected.previous_until })}`} /></div>
        <div class="sd-hero-breakdown"><span>Bán ra <b>{money(selected.summary.gross_revenue)}đ</b></span><i /><span>Hàng trả <b>−{money(selected.summary.return_revenue)}đ</b></span><i /><span>TB/đơn <b>{money(selected.summary.avg_order_value)}đ</b></span></div>
      </section>

      <div class="sd-metrics">
        <MetricCard icon="box" label="Số lượng thuần" value={`${qtyVN(selected.summary.net_qty)} SP`} sub={`${qtyVN(selected.summary.gross_qty)} bán · ${qtyVN(selected.summary.return_qty)} trả`} change={selected.changes.net_qty} tone="mint" />
        <MetricCard icon="receipt" label="Đơn bán" value={String(selected.summary.orders)} sub={`${selected.summary.returns} phiếu trả`} change={selected.changes.orders} tone="gold" />
        <MetricCard icon="users" label="Khách mua" value={String(selected.summary.customers)} sub={`${selected.summary.products} mã sản phẩm`} change={selected.changes.customers} tone="blue" />
        <MetricCard icon="banknote" label="Giá trị TB/đơn" value={`${compactMoney(selected.summary.avg_order_value)}đ`} sub="Trước khi trừ hàng trả" change={selected.changes.avg_order_value} tone="coral" />
      </div>

      <DataWarning coverage={data?.coverage} />
      {data?._stale && <div class="sd-warning"><Icon name="info" size={17} /><span>Đang hiển thị dữ liệu đã lưu vì thiết bị mất mạng.</span></div>}
      {!selectedHasTransactions && <section class="sd-panel"><EmptyState icon="📭">Ngày đang chọn chưa có giao dịch.</EmptyState></section>}
      {chartHasTransactions && <SalesTrend daily={selected.daily} selectedDay={selected.chart_selected_day} />}
      {selectedHasTransactions && <Ranking period={selected} />}

      <details class="sd-panel sd-method"><summary>Cách tính số liệu</summary><p><b>Số lượng thuần</b> = số lượng bán − số lượng trên phiếu trả đã xác nhận. <b>Doanh thu thuần</b> = doanh thu bán chưa VAT − giá trị hàng trả; đã gồm phí vận chuyển thu khách và chiết khấu của đơn.</p><p>Khách mua là số khách khác nhau có đơn bán trong kỳ. “Tuần này” tính từ thứ Hai; số so sánh tuần/tháng dùng cùng số ngày đã trôi qua của kỳ trước. Khoảng ngày tự chọn so với khoảng liền trước có cùng số ngày.</p></details>
    </>}
  </div>;
}
