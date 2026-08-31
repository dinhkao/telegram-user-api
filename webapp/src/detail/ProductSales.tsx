// Khối "Báo cáo bán ra" ở trang chi tiết SP (#/kho/:code, CHỈ VĂN PHÒNG) ←
// GET /api/profit/product/{code} (top_customers + chart theo ngày). Lazy-load
// bằng IntersectionObserver (endpoint quét full bảng orders — chỉ gọi khi khối
// lộ ra màn hình); đổi khoảng ngày qua ProfitDateBar (dùng chung trang lợi nhuận).
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, isOffice } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar, presetRange, type DateRange } from "./ProfitDateBar";
import { Icon } from "../ui/Icon";
import { EmptyState, ErrorState, LoadingInline } from "../ui/states";

// 2 chuỗi xem 1-lúc-1: màu theo app (doanh thu xanh dương như #/loi-nhuan)
const SERIES: [string, string, string][] = [
  ["revenue", "Doanh thu", "#3b82f6"],
  ["qty", "SL bán", "#a855f7"],
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
    const g = groups[key] || (groups[key] = { day: key, qty: 0, revenue: 0 });
    g.qty += c.qty; g.revenue += c.revenue;
  }
  return Object.keys(groups).sort().map((k) => groups[k]);
}

function SalesChart({ chart }: { chart: any[] }) {
  const [serie, setSerie] = useState("revenue");
  const [agg, setAgg] = useState("daily");
  if (!chart.length) return null;
  const data = aggregate(chart, agg);
  const color = SERIES.find(([k]) => k === serie)![2];
  const W = 900, H = 180, PAD = 4;
  const vals = data.map((c) => Number(c[serie]) || 0);
  const max = Math.max(...vals, 1);
  const bw = (W - PAD * 2) / data.length;
  const step = Math.max(1, Math.ceil(data.length / 10));
  return (
    <>
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
          <line x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} stroke="var(--muted)" stroke-width="0.5" />
          {data.map((c, i) => {
            const v = Number(c[serie]) || 0;
            const h = (v / max) * (H - PAD * 2);
            return (
              <g key={c.day}>
                <rect x={PAD + i * bw + 1} y={H - PAD - h} width={Math.max(1, bw - 2)}
                  height={Math.max(v > 0 ? 1 : 0, h)} rx={Math.min(2, bw / 4)} fill={color}>
                  <title>{c.day}: {fmtQty(c.qty)} · {money(c.revenue)}</title>
                </rect>
                {i % step === 0 && (
                  <text x={PAD + i * bw + bw / 2} y={H + 12} font-size="9" text-anchor="middle"
                    fill="currentColor" opacity="0.6">{agg === "monthly" ? c.day.slice(5, 7) : `${c.day.slice(8, 10)}/${c.day.slice(5, 7)}`}</text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </>
  );
}

// Cache theo MÃ (module scope): back về trang chi tiết SP là khối render ngay với
// đúng khoảng ngày đã chọn → useScrollMemory khôi phục vị trí không hụt chiều cao.
const _cache = new Map<string, { range: DateRange; data: any }>();

export function ProductSales({ code }: { code: string }) {
  const cached = _cache.get(code);
  const [range, setRange] = useState<DateRange>(() => cached?.range || presetRange("this_month"));
  const [data, setData] = useState<any>(cached?.data || null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const started = useRef(!!cached);
  const secRef = useRef<HTMLElement>(null);

  const load = () => {
    setErr("");
    setLoading(true);
    getJSON(`/api/profit/product/${encodeURIComponent(code)}?since=${range.since}&until=${range.until}`, { cache: false })
      .then((j) => { setData(j); _cache.set(code, { range, data: j }); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải báo cáo bán ra"))
      .finally(() => setLoading(false));
  };
  // Đổi mã SP → về trạng thái cache của mã đó (hoặc chưa tải, chờ khối lộ ra)
  useEffect(() => {
    const c = _cache.get(code);
    started.current = !!c;
    setData(c?.data || null);
    if (c) setRange(c.range);
  }, [code]);
  useEffect(() => {
    const el = secRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) { started.current = true; load(); }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [code]);
  useEffect(() => { if (started.current) load(); }, [range.since, range.until]);

  if (!isOffice()) return null;
  const t = data?.totals;
  const tops = (data?.top_customers || []).slice(0, 10);
  const maxRev = tops.length ? Math.max(...tops.map((c: any) => c.revenue), 1) : 1;
  return (
    <section class="card" ref={secRef}>
      <div class="row space">
        <label class="card-label" style={{ margin: 0 }}>Báo cáo bán ra</label>
        <a class="btn small" href={`#/loi-nhuan/sp/${encodeURIComponent(code)}`}>
          <Icon name="chart" size={14} /> Lợi nhuận →
        </a>
      </div>
      {!started.current || (loading && !data) ? (
        <div class="muted small"><LoadingInline /></div>
      ) : err && !data ? (
        <ErrorState msg={err} onRetry={load} />
      ) : !data ? null : (
        <>
          <ProfitDateBar range={range} onChange={setRange} />
          <div class="pf-cards">
            <div class="card pf-card"><h4>SL bán</h4><b>{fmtQty(t.qty)}</b></div>
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Số đơn</h4><b>{data.orders.length}</b></div>
            <div class="card pf-card"><h4>Số khách</h4><b>{t.customers || 0}</b></div>
          </div>
          {!data.orders.length ? (
            <EmptyState>Không có lần bán nào trong khoảng ngày.</EmptyState>
          ) : (
            <>
              <SalesChart chart={data.chart || []} />
              <div class="ie-head" style={{ marginTop: "8px" }}>
                Top khách hàng <span class="ie-count">{tops.length}</span>
              </div>
              <table class="inv-mini pf-table">
                <thead><tr><th>Khách</th><th class="num">SL</th><th class="num">Doanh thu</th><th class="num">Đơn</th></tr></thead>
                <tbody>{tops.map((c: any) => (
                  <tr key={c.name}>
                    <td>
                      <a href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}`}>{c.name}</a>
                      <div style={{ height: "3px", borderRadius: "2px", background: "#3b82f6", opacity: 0.55, width: `${Math.max(3, Math.round((c.revenue / maxRev) * 100))}%` }} />
                    </td>
                    <td class="num">{fmtQty(c.qty)}</td>
                    <td class="num">{money(c.revenue)}</td>
                    <td class="num">{c.orders}</td>
                  </tr>
                ))}</tbody>
              </table>
            </>
          )}
        </>
      )}
    </section>
  );
}
