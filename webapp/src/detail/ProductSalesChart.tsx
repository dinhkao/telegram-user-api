// Biểu đồ cột SVG thuần cho khối "Báo cáo bán ra" (ProductSales, chi tiết SP).
// Chuỗi Ngày/Tuần/Tháng × Doanh thu/SL; ĐIỀN NGÀY TRỐNG trong khoảng đã chọn để
// trục thời gian đều (ngày không bán = cột 0, không bị "dồn" lại); CHẠM cột để
// xem số (title hover không chạy trên điện thoại); đường TB nét đứt để so từng cột.
import { useEffect, useState } from "preact/hooks";
import { money, fmtQty } from "../format";

export type SalesPt = { day: string; qty: number; revenue: number };

const SERIES: [string, string, string][] = [
  ["revenue", "Doanh thu", "#3b82f6"],
  ["qty", "SL bán − trả", "#a855f7"],
];
const AGGS: [string, string][] = [["daily", "Ngày"], ["weekly", "Tuần"], ["monthly", "Tháng"]];
const MAX_FILL_DAYS = 400;   // khoảng dài hơn thì không điền (chuỗi thô vẫn vẽ được)

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Điền ngày không bán = 0 giữa since..until (client biết khoảng, server chỉ trả ngày có bán). */
export function fillDays(chart: SalesPt[], since?: string, until?: string): SalesPt[] {
  if (!since || !until || since > until) return chart;
  const a = new Date(since + "T00:00:00"), b = new Date(until + "T00:00:00");
  if (isNaN(+a) || isNaN(+b) || (+b - +a) / 86400000 > MAX_FILL_DAYS) return chart;
  const have = new Map(chart.map((c) => [c.day, c]));
  const out: SalesPt[] = [];
  for (const d = new Date(a); d <= b; d.setDate(d.getDate() + 1)) {
    const k = iso(d);
    out.push(have.get(k) || { day: k, qty: 0, revenue: 0 });
  }
  return out;
}

export function aggregate(chart: SalesPt[], mode: string): SalesPt[] {
  if (mode === "daily") return chart;
  const groups: Record<string, SalesPt> = {};
  for (const c of chart) {
    let key: string;
    if (mode === "weekly") {
      const dt = new Date(c.day + "T00:00:00");
      dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));   // về thứ 2
      key = iso(dt);
    } else key = c.day.slice(0, 7);
    const g = groups[key] || (groups[key] = { day: key, qty: 0, revenue: 0 });
    g.qty += c.qty; g.revenue += c.revenue;
  }
  return Object.keys(groups).sort().map((k) => groups[k]);
}

const tick = (day: string, agg: string) =>
  agg === "monthly" ? `T${parseInt(day.slice(5, 7), 10)}` : `${day.slice(8, 10)}/${day.slice(5, 7)}`;
const ptLabel = (day: string, agg: string) =>
  agg === "monthly" ? `Tháng ${parseInt(day.slice(5, 7), 10)}/${day.slice(0, 4)}`
    : agg === "weekly" ? `Tuần từ ${tick(day, agg)}` : tick(day, agg);
const fmtVal = (serie: string, v: number) => serie === "qty" ? fmtQty(Math.round(v * 100) / 100) : money(Math.round(v));

export function ProductSalesChart({ chart, since, until }: { chart: SalesPt[]; since?: string; until?: string }) {
  const [serie, setSerie] = useState("revenue");
  const [agg, setAgg] = useState("daily");
  const [sel, setSel] = useState(-1);
  useEffect(() => setSel(-1), [chart, agg, serie]);
  if (!chart.length) return null;
  const data = aggregate(fillDays(chart, since, until), agg);
  const [, serieLabel, color] = SERIES.find(([k]) => k === serie)!;
  const W = 900, H = 180, PAD = 4, TOP = 16;
  const vals = data.map((c) => Number((c as any)[serie]) || 0);
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0);
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  const peak = vals.indexOf(Math.max(...vals));
  const bw = (W - PAD * 2) / data.length;
  const step = Math.max(1, Math.ceil(data.length / 10));
  const yOf = (v: number) => H - PAD - ((v - min) / (max - min)) * (H - PAD - TOP);
  const cur = sel >= 0 && sel < data.length ? data[sel] : null;
  const unitName = agg === "daily" ? "ngày" : agg === "weekly" ? "tuần" : "tháng";
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
      <div class="ps-readout">
        {cur ? (
          <><b>{ptLabel(cur.day, agg)}</b> · {fmtQty(cur.qty)} · {money(cur.revenue)}
            <button class="ps-readout-x" onClick={() => setSel(-1)} aria-label="Bỏ chọn">×</button></>
        ) : (
          <span class="muted">TB {fmtVal(serie, avg)}/{unitName} · cao nhất {ptLabel(data[peak].day, agg)} ({fmtVal(serie, vals[peak])}) · chạm cột để xem số</span>
        )}
      </div>
      <div style="overflow-x:auto">
        <svg viewBox={`0 0 ${W} ${H + 18}`} style="width:100%;min-width:480px" onClick={() => setSel(-1)}>
          <line x1={PAD} x2={W - PAD} y1={yOf(0)} y2={yOf(0)} stroke="var(--muted)" stroke-width="0.5" />
          {avg !== 0 && (
            <g opacity="0.7">
              <line x1={PAD} x2={W - PAD} y1={yOf(avg)} y2={yOf(avg)} stroke={color} stroke-width="0.8" stroke-dasharray="4 3" />
              <text x={W - PAD - 2} y={yOf(avg) - 3} font-size="9" text-anchor="end" fill={color}>TB {fmtVal(serie, avg)}</text>
            </g>
          )}
          <text x={PAD + 2} y={10} font-size="9" fill="currentColor" opacity="0.6">{serieLabel} · max {fmtVal(serie, max)}</text>
          {data.map((c, i) => {
            const v = vals[i];
            const h = Math.abs(yOf(v) - yOf(0));
            const on = sel === i;
            return (
              <g key={c.day} onClick={(e: Event) => { e.stopPropagation(); setSel(on ? -1 : i); }} style="cursor:pointer">
                <rect x={PAD + i * bw} y={TOP} width={bw} height={H - TOP} fill="transparent" />
                <rect x={PAD + i * bw + 1} y={Math.min(yOf(0), yOf(v))} width={Math.max(1, bw - 2)}
                  height={Math.max(v !== 0 ? 1 : 0, h)} rx={Math.min(2, bw / 4)} fill={v < 0 ? "var(--danger)" : color}
                  opacity={sel < 0 || on ? 1 : 0.45} stroke={on ? "var(--ink)" : "none"} stroke-width="1">
                  <title>{ptLabel(c.day, agg)}: {fmtQty(c.qty)} · {money(c.revenue)}</title>
                </rect>
                {(i % step === 0 || on) && (
                  <text x={PAD + i * bw + bw / 2} y={H + 12} font-size="9" text-anchor="middle"
                    fill="currentColor" opacity={on ? 1 : 0.6} font-weight={on ? "700" : "400"}>{tick(c.day, agg)}</text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </>
  );
}
