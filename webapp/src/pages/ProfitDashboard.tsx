// Dashboard LỢI NHUẬN native (#/loi-nhuan, CHỈ văn phòng) — thay bộ trang HTML
// /loi-nhuan/* cũ (gỡ 2026-08-26), giữ ĐỦ tính năng bản gốc: chọn kỳ + LỌC theo
// mã SP/khách (debounce, áp summary/bảng/feed — top 5 vẫn toàn cảnh), thẻ tóm
// tắt so % kỳ trước + LÃI THỰC, nút 🔒 đóng băng giá vốn, 3 tab: Đơn hàng (feed
// + chip SP) · Sản phẩm (sửa giá vốn hàng loạt + lọc SP chưa có vốn) · Biểu đồ
// (SVG: gộp Ngày/Tuần/Tháng, 4 chuỗi DT/Vốn/Lãi/LN sau vay + đường Biên LN%).
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, postJSON, isOffice } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar, Chg, presetRange, type DateRange } from "../detail/ProfitDateBar";
import { ProfitOrdersFeed } from "../detail/ProfitOrdersFeed";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

function SummaryCards({ s }: { s: any }) {
  return (
    <>
      <div class="pf-cards">
        <div class="card pf-card"><h4>Doanh thu</h4><b>{money(s.revenue)}</b><Chg v={s.changes?.revenue} /></div>
        <div class="card pf-card"><h4>Giá vốn</h4><b>{money(s.cost)}</b><Chg v={s.changes?.cost} /></div>
        <div class="card pf-card"><h4>Lãi gộp</h4><b class={s.profit >= 0 ? "t-ok" : "t-danger"}>{money(s.profit)}</b><Chg v={s.changes?.profit} /></div>
        <div class="card pf-card"><h4>Số đơn</h4><b>{s.orders}</b><Chg v={s.changes?.orders} /></div>
      </div>
      <div class="card pf-real">
        <h4>LÃI THỰC (sau tiền vay)</h4>
        <b>{money(s.real_profit)}</b>
        <div class="small">vay phân bổ kỳ này: {money(s.loan)} · biên {s.margin}%</div>
        {s.prev_label ? <div class="small" style="opacity:.8">so kỳ trước {s.prev_label}: lãi {money(s.prev?.profit || 0)}</div> : null}
      </div>
    </>
  );
}

function TopLists({ d }: { d: any }) {
  return (
    <div class="pf-tops">
      <div class="card">
        <div class="ie-head">Top khách (lãi)</div>
        {(d.top_customers || []).map((c: any, i: number) => (
          <a key={c.name} class="pf-top-row" href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}`}>
            <span class="pf-rank">{i + 1}</span>
            <span class="pf-top-name">{c.name}</span>
            <span class="num"><b class={c.profit >= 0 ? "t-ok" : "t-danger"}>{money(c.profit)}</b>
              <span class="muted small"> · {c.orders} đơn</span></span>
          </a>
        ))}
      </div>
      <div class="card">
        <div class="ie-head">Top sản phẩm (lãi)</div>
        {(d.top_products || []).map((p: any, i: number) => (
          <a key={p.code} class="pf-top-row" href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}`}>
            <span class="pf-rank">{i + 1}</span>
            <span class="pf-top-name">{p.code}</span>
            <span class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}</b>
              <span class="muted small"> · {fmtQty(p.qty)}</span></span>
          </a>
        ))}
      </div>
    </div>
  );
}

// Tab Sản phẩm: bảng lãi theo SP + Ô GIÁ VỐN MỚI sửa hàng loạt → POST /api/profit/costs
function ProductCostTable({ products, onSaved }: { products: any[]; onSaved: () => void }) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [onlyMissing, setOnlyMissing] = useState(false);   // "Chọn SP chưa có giá vốn" bản gốc
  const missing = products.filter((p) => !p.cost_price).length;
  const shown = onlyMissing ? products.filter((p) => !p.cost_price) : products;
  const dirty = Object.entries(edits).filter(([, v]) => v.trim() !== "");
  const save = async () => {
    const updates: Record<string, number> = {};
    for (const [code, v] of dirty) {
      const n = parseInt(v.replace(/[.,\s]/g, ""), 10);
      if (!isNaN(n) && n >= 0) updates[code] = n;
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
            ⚠ Chưa có giá vốn ({missing})
          </button>
        </div>
      )}
      <table class="inv-mini pf-table">
        <thead><tr><th>SP</th><th class="num">Vốn</th><th class="num">Vốn mới</th><th class="num">SL</th><th class="num">Lãi</th></tr></thead>
        <tbody>
          {shown.map((p) => (
            <tr key={p.code}>
              <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}`} title={p.name}>{p.code}</a></td>
              <td class="num">{p.cost_price ? money(p.cost_price) : <span class="t-warn">chưa có</span>}</td>
              <td class="num"><input class="pf-cost-inp" inputMode="numeric" placeholder="giá"
                value={edits[p.code] ?? ""}
                onInput={(e: any) => setEdits((prev) => ({ ...prev, [p.code]: e.target.value }))} /></td>
              <td class="num">{fmtQty(p.qty)}</td>
              <td class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Tab Biểu đồ (SVG thuần): gộp Ngày/Tuần/Tháng + chọn chuỗi (DT/Vốn/Lãi/LN sau
// vay) + đường Biên LN% (trục phải, như Chart.js bản gốc)
const SERIES: [string, string, string][] = [
  ["revenue", "Doanh thu", "#3b82f6"], ["cost", "Giá vốn", "#ef4444"],
  ["profit", "Lãi gộp", "#22c55e"], ["real_profit", "LN sau vay", "#a855f7"],
];
const AGGS: [string, string][] = [["daily", "Ngày"], ["weekly", "Tuần"], ["monthly", "Tháng"]];

function aggregate(chart: any[], mode: string): any[] {
  if (mode === "daily") return chart;
  const groups: Record<string, any> = {};
  for (const c of chart) {
    let key: string;
    if (mode === "weekly") {
      const dt = new Date(c.day);
      const mon = new Date(dt);
      mon.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));   // về thứ 2
      key = `${mon.getFullYear()}-${String(mon.getMonth() + 1).padStart(2, "0")}-${String(mon.getDate()).padStart(2, "0")}`;
    } else key = c.day.slice(0, 7);
    const g = groups[key] || (groups[key] = { day: key, revenue: 0, cost: 0, profit: 0, real_profit: 0 });
    g.revenue += c.revenue; g.cost += c.cost || 0; g.profit += c.profit; g.real_profit += c.real_profit;
  }
  return Object.keys(groups).sort().map((k) => groups[k]);
}

function ProfitChart({ chart }: { chart: any[] }) {
  const [serie, setSerie] = useState("real_profit");
  const [agg, setAgg] = useState("daily");
  if (!chart.length) return <EmptyState>Chưa có dữ liệu trong khoảng ngày này.</EmptyState>;
  const data = aggregate(chart, agg);
  const color = SERIES.find(([k]) => k === serie)![2];
  const W = 900, H = 240, PAD = 4;
  const vals = data.map((c) => Number(c[serie]) || 0);
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0);
  const span = max - min || 1;
  const bw = (W - PAD * 2) / data.length;
  const y0 = PAD + (max / span) * (H - PAD * 2);
  // đường Biên LN% (profit/revenue) — scale 0..100% vào chiều cao khung
  const marginPts = data.map((c, i) => {
    const m = c.revenue > 0 ? (c.profit / c.revenue) * 100 : 0;
    const y = H - PAD - Math.max(0, Math.min(100, m)) / 100 * (H - PAD * 2);
    return `${PAD + i * bw + bw / 2},${y}`;
  }).join(" ");
  return (
    <div class="card">
      <div class="chips">
        {AGGS.map(([k, label]) => (
          <button key={k} class={"chip" + (agg === k ? " active" : "")} onClick={() => setAgg(k)}>{label}</button>
        ))}
        <span style="width:8px" />
        {SERIES.map(([k, label, c]) => (
          <button key={k} class={"chip" + (serie === k ? " active" : "")}
            style={serie === k ? `background:${c};border-color:${c};color:#fff` : ""}
            onClick={() => setSerie(k)}>{label}</button>
        ))}
      </div>
      <div style="overflow-x:auto">
        <svg viewBox={`0 0 ${W} ${H + 18}`} style="width:100%;min-width:480px">
          <line x1={PAD} x2={W - PAD} y1={y0} y2={y0} stroke="var(--muted)" stroke-width="0.5" />
          {data.map((c, i) => {
            const v = Number(c[serie]) || 0;
            const h = (Math.abs(v) / span) * (H - PAD * 2);
            const y = v >= 0 ? y0 - h : y0;
            const m = c.revenue > 0 ? ((c.profit / c.revenue) * 100).toFixed(1) : "0";
            return (
              <g key={c.day}>
                <rect x={PAD + i * bw + 1} y={y} width={Math.max(1, bw - 2)} height={Math.max(1, h)} fill={color}>
                  <title>{c.day}: {money(v)} · biên {m}%</title>
                </rect>
                {data.length <= 31 && i % Math.ceil(data.length / 10) === 0 && (
                  <text x={PAD + i * bw + bw / 2} y={H + 12} font-size="9" text-anchor="middle"
                    fill="currentColor" opacity="0.6">{agg === "monthly" ? c.day.slice(5, 7) : `${c.day.slice(8, 10)}/${c.day.slice(5, 7)}`}</text>
                )}
              </g>
            );
          })}
          {data.length > 1 && <polyline points={marginPts} fill="none" stroke="#f59e0b" stroke-width="1.5" opacity="0.9" />}
        </svg>
      </div>
      <div class="muted small">Đường vàng = Biên LN % (0–100%, trục phải ẩn) · cột = {SERIES.find(([k]) => k === serie)![1]}</div>
    </div>
  );
}

export function ProfitDashboard() {
  const [range, setRange] = useState<DateRange>(() => presetRange("today"));
  const [fp, setFp] = useState("");            // lọc mã SP (debounce)
  const [fc, setFc] = useState("");            // lọc khách
  const [flt, setFlt] = useState({ product: "", customer: "" });   // bản đã debounce
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<string>(() => sessionStorage.getItem("pf_tab") || "don");
  const pickTab = (t: string) => { setTab(t); sessionStorage.setItem("pf_tab", t); };
  const t = useRef<number>();
  useEffect(() => {
    clearTimeout(t.current);
    t.current = window.setTimeout(() => setFlt({ product: fp, customer: fc }), 300);
    return () => clearTimeout(t.current);
  }, [fp, fc]);

  const load = () => {
    setErr("");
    const p = new URLSearchParams({ since: range.since, until: range.until });
    if (flt.product.trim()) p.set("product", flt.product.trim());
    if (flt.customer.trim()) p.set("customer", flt.customer.trim());
    getJSON(`/api/profit/dashboard?${p}`, { cache: false })
      .then(setData).catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [range.since, range.until, flt.product, flt.customer]);

  // 🔒 đóng băng giá vốn — như nút trên thanh lọc của bản gốc
  const freeze = async () => {
    if (!(await confirmDialog(
      "Đóng băng giá vốn vào tất cả đơn hàng? Giá vốn hiện tại sẽ được lưu vào đơn và không đổi khi cập nhật giá mới.",
      { okLabel: "Đóng băng" }))) return;
    setBusy(true);
    try {
      const j = await postJSON("/api/profit/freeze-costs", {});
      toast(`Đã đóng băng giá vốn vào ${j.updated} đơn`, "ok");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  if (!isOffice()) return <div class="prod-detail"><PageHead fallback="#/home" title="Lợi nhuận" /><EmptyState>Chỉ văn phòng được xem trang lợi nhuận.</EmptyState></div>;
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/home" title="Lợi nhuận" /><ErrorState msg={err} onRetry={load} /></div>;

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title="Lợi nhuận" sub={`${range.since} → ${range.until}`}
        right={<span class="row">
          <a class="btn small" href="#/loi-nhuan/khach"><Icon name="users" size={14} /> Khách</a>
          <a class="btn small" href="#/loi-nhuan/cai-dat"><Icon name="settings" size={14} /></a>
        </span>} />
      <ProfitDateBar range={range} onChange={setRange} />
      <div class="card pf-filterbar">
        <input class="note-inp" placeholder="Lọc theo mã SP" value={fp}
          onInput={(e: any) => setFp(e.target.value)} />
        <input class="note-inp" placeholder="Lọc theo khách hàng" value={fc}
          onInput={(e: any) => setFc(e.target.value)} />
        {(fp || fc) && <button class="btn small" onClick={() => { setFp(""); setFc(""); }}>Xoá lọc</button>}
        <button class="btn small" disabled={busy} onClick={freeze}>🔒 Đóng băng giá vốn</button>
      </div>
      {!data ? <Loading /> : (
        <>
          <SummaryCards s={data.summary} />
          <TopLists d={data} />
          <div class="seg mt-2">
            {[["don", "Đơn hàng"], ["sp", "Sản phẩm"], ["chart", "Biểu đồ"]].map(([k, label]) => (
              <button key={k} class={"seg-btn" + (tab === k ? " active" : "")} onClick={() => pickTab(k)}>{label}</button>
            ))}
          </div>
          {tab === "don" && <ProfitOrdersFeed range={range} product={flt.product} customer={flt.customer} />}
          {tab === "sp" && <ProductCostTable products={data.products || []} onSaved={load} />}
          {tab === "chart" && <ProfitChart chart={data.chart || []} />}
        </>
      )}
    </div>
  );
}
