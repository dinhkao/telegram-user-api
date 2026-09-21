import { useEffect, useState } from "preact/hooks";
import { QUICK_PRESETS, MORE_PRESETS, presetRange, validRange, rangeDays, displayRange, vnToday, type DateRange } from "./profitDates";
export { presetRange, type DateRange } from "./profitDates";

export function ProfitDateBar({ range, onChange }: { range: DateRange; onChange: (r: DateRange) => void }) {
  const [draft, setDraft] = useState(range);
  useEffect(() => { setDraft(range); }, [range.since, range.until]);
  const presets = [...QUICK_PRESETS, ...MORE_PRESETS];
  const active = presets.find(([k]) => {
    const r = presetRange(k);
    return r.since === range.since && r.until === range.until;
  })?.[0];
  const fullMonth = presetRange(`month_${range.since.slice(0, 7).replace("-", "_")}`);
  const monthValue = range.since === fullMonth.since && range.until === fullMonth.until ? range.since.slice(0, 7) : "";
  const dirty = draft.since !== range.since || draft.until !== range.until;
  const chips = (items: readonly (readonly [string, string])[]) => items.map(([k, label]) => (
    <button key={k} type="button" class={"chip" + (active === k ? " active" : "")}
      aria-pressed={active === k} onClick={() => onChange(presetRange(k))}>{label}</button>
  ));
  return (
    <div class="card pf-datebar">
      <div class="pf-section-label">Kỳ báo cáo <span>Giờ Việt Nam</span></div>
      <div class="chips pf-presets">{chips(QUICK_PRESETS)}</div>
      <details class="pf-more-dates">
        <summary>Thêm mốc thời gian{MORE_PRESETS.some(([k]) => k === active) ? ` · ${presets.find(([k]) => k === active)?.[1]}` : ""}</summary>
        <div class="chips pf-presets">{chips(MORE_PRESETS)}</div>
        <label class="pf-month-pick">Chọn tháng / năm
          <input aria-label="Chọn tháng và năm" type="month" value={monthValue} onChange={(e: any) => {
            const v = e.currentTarget.value;
            if (/^\d{4}-\d{2}$/.test(v)) onChange(presetRange(`month_${v.replace("-", "_")}`));
          }} />
        </label>
      </details>
      <form class="pf-dates" onSubmit={e => { e.preventDefault(); if (validRange(draft)) onChange(draft); }}>
        <label>Từ ngày<input aria-label="Từ ngày" type="date" required value={draft.since}
          onInput={(e: any) => setDraft({ ...draft, since: e.currentTarget.value })} /></label>
        <label>Đến ngày<input aria-label="Đến ngày" type="date" required value={draft.until}
          onInput={(e: any) => setDraft({ ...draft, until: e.currentTarget.value })} /></label>
        <button type="submit" class="btn small" disabled={!dirty || !validRange(draft)}>Áp dụng</button>
      </form>
      {dirty && !validRange(draft) && <p class="small t-danger" role="alert">Chọn đủ ngày, ngày bắt đầu ≤ ngày kết thúc; tối đa 3.660 ngày.</p>}
      <div class="pf-period-label">{displayRange(range)} <b>· {rangeDays(range)} ngày</b>
        {range.until > vnToday() && <span class="t-warn"> · Có ngày trong tương lai</span>}
      </div>
    </div>
  );
}

export function Chg({ v, nullLabel = "kỳ trước bằng 0", neutral = false }: {
  v: number | null | undefined; nullLabel?: string; neutral?: boolean;
}) {
  if (v === null || v === undefined) return <span class="pf-chg new">{nullLabel}</span>;
  return <span class={"pf-chg " + (neutral || v === 0 ? "new" : v > 0 ? "up" : "down")}>
    {v > 0 ? "▲" : v < 0 ? "▼" : "="} {Math.abs(v).toFixed(1)}%
  </span>;
}
