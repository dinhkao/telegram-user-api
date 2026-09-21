import { useState } from "preact/hooks";
import { money } from "../format";
import { aggregateProfit, grossMargin, type ProfitPoint } from "./profitChartData";
import { EmptyState } from "../ui/states";
const SERIES = [
  ["revenue", "Doanh thu", "#2563eb"], ["cost", "Giá vốn", "#b45309"],
  ["profit", "Lãi gộp", "#188038"], ["real_profit", "Lãi sau vay", "#0f766e"],
] as const;
const compactMoney = (v: number) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(v);
export function ProfitChart({ chart }: { chart: ProfitPoint[] }) {
  const [selectedSerie, setSerie] = useState<(typeof SERIES)[number][0]>("real_profit");
  const [aggregation, setAggregation] = useState("auto");
  const agg = aggregation === "auto" ? chart.length > 90 ? "monthly" : chart.length > 31 ? "weekly" : "daily" : aggregation;
  const [selected, setSelected] = useState("");
  if (!chart.length) return <EmptyState>Chưa có dữ liệu trong khoảng ngày này.</EmptyState>;
  const availableSeries = chart.some(p => p.real_profit === null) ? SERIES.filter(([k]) => k !== "real_profit") : SERIES;
  const serie = availableSeries.some(([k]) => k === selectedSerie) ? selectedSerie : "profit";
  const value = (p: ProfitPoint) => p[serie] ?? 0;
  const hasLoan = availableSeries.some(([k]) => k === "real_profit");
  const data = aggregateProfit(chart, agg), chosen = data.find(p => p.day === selected);
  const series = SERIES.find(([k]) => k === serie)!;
  const W = 780, H = 280, L = 62, R = 60, T = 24, B = 36;
  const vals = data.map(value);
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0), span = max - min;
  const margins = data.map(grossMargin);
  const marginMax = Math.max(10, ...margins.filter((v): v is number => v !== null));
  const marginMin = Math.min(0, ...margins.filter((v): v is number => v !== null));
  const plotH = H - T - B, bw = (W - L - R) / data.length;
  const y = (v: number) => T + (max - v) / span * plotH;
  const my = (v: number) => T + (marginMax - v) / (marginMax - marginMin) * plotH;
  const x = (i: number) => L + (i + .5) * bw;
  const periodLabel = (day: string) => day.length === 7 ? `${day.slice(5)}/${day.slice(0, 4)}` : `${agg === "weekly" ? "Tuần " : ""}${day.slice(8)}/${day.slice(5, 7)}/${day.slice(0, 4)}`;
  const label = `${series[1]} theo ${agg === "daily" ? "ngày" : agg === "weekly" ? "tuần" : "tháng"}`;
  let path = "", connected = false;
  margins.forEach((m, i) => { if (m === null) connected = false; else { path += `${connected ? "L" : "M"}${x(i)},${my(m)} `; connected = true; } });
  return <div class="card pf-chart">
    <div class="ie-head">Xu hướng cả kỳ <span class="ie-count">{chart.length} ngày</span></div>
    <div class="chips pf-presets">{[["auto", "Tự động"], ["daily", "Ngày"], ["weekly", "Tuần"], ["monthly", "Tháng"]].map(([k, l]) =>
      <button class={"chip" + (aggregation === k ? " active" : "")} aria-pressed={aggregation === k} onClick={() => { setAggregation(k); setSelected(""); }}>{l}</button>)}</div>
    <div class="chips pf-presets">{availableSeries.map(([k, l, color]) => <button class={"chip" + (serie === k ? " active" : "")}
      style={serie === k ? { background: color, borderColor: color, color: "white" } : {}}
      aria-pressed={serie === k} onClick={() => setSerie(k)}>{l}</button>)}</div>
    <div class="pf-table-scroll">
      <svg viewBox={`0 0 ${W} ${H}`} class="pf-chart-svg" role="img" aria-label={`${label}; đường màu vàng là biên lãi gộp. Bảng số liệu bên dưới.`}>
        <text x={L} y="12" font-size="10" fill="var(--muted)">VND</text><text x={W - R} y="12" font-size="10" fill="var(--warn)">Biên %</text>
        {[0, .25, .5, .75, 1].map(t => <g>
          <line x1={L} x2={W - R} y1={T + t * plotH} y2={T + t * plotH} stroke="var(--border)" stroke-dasharray="3 4" />
          <text x={L - 8} y={T + t * plotH + 3} font-size="10" text-anchor="end" fill="var(--muted)">{compactMoney(max - t * span)}</text>
          <text x={W - R + 8} y={T + t * plotH + 3} font-size="10" fill="var(--warn)">{(marginMax - t * (marginMax - marginMin)).toFixed(0)}%</text>
        </g>)}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="var(--muted)" />
        {data.map((p, i) => <g key={p.day}>
          <rect x={L + i * bw + bw * .1} width={bw * .8} y={Math.min(y(0), y(value(p)))} height={Math.abs(y(value(p)) - y(0))}
            rx={Math.min(2, bw * .1)} fill={value(p) < 0 ? "var(--danger)" : series[2]} opacity={selected && selected !== p.day ? .5 : .9}>
            <title>{periodLabel(p.day)}: {money(value(p))} · biên {margins[i]?.toFixed(1) ?? "—"}%</title>
          </rect>
          <rect x={L + i * bw} width={bw} y={T} height={plotH} fill="transparent" onClick={() => setSelected(p.day)} style="cursor:pointer" />
          {i % Math.max(1, Math.ceil(data.length / 7)) === 0 && <text x={x(i)} y={H - 13} font-size="10" text-anchor="middle" fill="var(--muted)">
            {p.day.length === 7 ? `${p.day.slice(5)}/${p.day.slice(2, 4)}` : `${p.day.slice(8)}/${p.day.slice(5, 7)}`}</text>}
        </g>)}
        <path d={path} fill="none" stroke="#b26b00" stroke-width="2" pointer-events="none" />
        {margins.map((m, i) => m !== null && <circle cx={x(i)} cy={my(m)} r={data.length < 40 ? 2.5 : 1} fill="#b26b00" pointer-events="none" />)}
      </svg>
    </div>
    <p class="muted small">Cột: {series[1]} · Đường vàng: biên lãi gộp (trục phải, có cả số âm). Kỳ không có doanh thu dương hoặc thiếu căn cứ giá vốn không tính biên. Lãi của kỳ thiếu vốn chỉ là phần đã xác định.</p>
    <label class="pf-chart-picker">Xem chi tiết kỳ
      <select aria-label="Xem chi tiết kỳ" value={chosen?.day || ""} onChange={(e: any) => setSelected(e.currentTarget.value)}>
        <option value="">Chọn ngày / tuần / tháng</option>{data.map(p => <option value={p.day}>{periodLabel(p.day)}</option>)}
      </select>
    </label>
    {chosen && <div class="pf-chart-selection" aria-live="polite"><b>{periodLabel(chosen.day)}</b><span>{chosen.orders || 0} đơn · Doanh thu {money(chosen.revenue)}</span>
      <span>Lãi gộp {money(chosen.profit)}{hasLoan && <> · Sau lãi vay {money(chosen.real_profit ?? 0)}</>}</span></div>}
    <details class="pf-method"><summary>Bảng số liệu đầy đủ ({data.length} kỳ)</summary>
      <div class="pf-table-scroll"><table class="inv-mini pf-table"><thead><tr><th>Kỳ</th><th class="num">Đơn</th><th class="num">Doanh thu</th><th class="num">Giá vốn</th><th class="num">Lãi gộp</th>{hasLoan && <th class="num">Sau lãi vay</th>}<th class="num">Biên gộp</th></tr></thead>
        <tbody>{data.map(p => <tr><td>{periodLabel(p.day)}</td><td class="num">{p.orders || 0}</td><td class="num">{money(p.revenue)}</td><td class="num">{money(p.cost)}</td><td class="num">{money(p.profit)}</td>{hasLoan && <td class="num">{money(p.real_profit ?? 0)}</td>}<td class="num">{grossMargin(p)?.toFixed(1) ?? "—"}%</td></tr>)}</tbody>
      </table></div>
    </details>
  </div>;
}
