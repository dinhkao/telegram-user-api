// Thanh chọn khoảng ngày cho các trang LỢI NHUẬN (#/loi-nhuan*): chip preset
// (Hôm nay/Tuần này/30 ngày/Tháng N…) + 2 ô ngày tự do. Ngày tính theo đồng hồ
// máy (như bản legacy). Dùng chung: ProfitDashboard/Customers/Customer/Product.
import { useState } from "preact/hooks";

export type DateRange = { since: string; until: string };

const fmt = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function presetRange(p: string): DateRange {
  const now = new Date();
  const today = fmt(now);
  switch (p) {
    case "today": return { since: today, until: today };
    case "yesterday": { const y = new Date(now); y.setDate(y.getDate() - 1); return { since: fmt(y), until: fmt(y) }; }
    case "this_week": { const m = new Date(now); m.setDate(m.getDate() - ((m.getDay() + 6) % 7)); return { since: fmt(m), until: today }; }
    case "7days": { const d = new Date(now); d.setDate(d.getDate() - 7); return { since: fmt(d), until: today }; }
    case "30days": { const d = new Date(now); d.setDate(d.getDate() - 30); return { since: fmt(d), until: today }; }
    case "this_month": return { since: fmt(new Date(now.getFullYear(), now.getMonth(), 1)), until: today };
    case "last_month": return {
      since: fmt(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      until: fmt(new Date(now.getFullYear(), now.getMonth(), 0)),
    };
    default: {
      const m = p.startsWith("month_") ? parseInt(p.slice(6), 10) : NaN;
      if (m >= 1 && m <= 12) {
        return { since: fmt(new Date(now.getFullYear(), m - 1, 1)), until: fmt(new Date(now.getFullYear(), m, 0)) };
      }
      return { since: today, until: today };
    }
  }
}

const PRESETS: [string, string][] = [
  ["today", "Hôm nay"], ["yesterday", "Hôm qua"], ["this_week", "Tuần này"],
  ["7days", "7 ngày"], ["30days", "30 ngày"], ["this_month", "Tháng này"],
  ["last_month", "Tháng trước"],
  ...Array.from({ length: 12 }, (_, i) => [`month_${i + 1}`, `Th${i + 1}`] as [string, string]),
];

export function ProfitDateBar({ range, onChange }: {
  range: DateRange;
  onChange: (r: DateRange) => void;
}) {
  const [active, setActive] = useState("today");
  return (
    <div class="card pf-datebar">
      <div class="chips pf-presets">
        {PRESETS.map(([k, label]) => (
          <button key={k} class={"chip" + (active === k ? " active" : "")}
            onClick={() => { setActive(k); onChange(presetRange(k)); }}>{label}</button>
        ))}
      </div>
      <div class="row pf-dates">
        <input type="date" value={range.since}
          onChange={(e: any) => { setActive(""); onChange({ ...range, since: e.target.value }); }} />
        <span class="muted">→</span>
        <input type="date" value={range.until}
          onChange={(e: any) => { setActive(""); onChange({ ...range, until: e.target.value }); }} />
      </div>
    </div>
  );
}

// % thay đổi so kỳ trước: null = kỳ trước không có dữ liệu ("mới")
export function Chg({ v }: { v: number | null | undefined }) {
  if (v === null || v === undefined) return <span class="pf-chg new">mới</span>;
  const up = v >= 0;
  return <span class={"pf-chg " + (up ? "up" : "down")}>{up ? "▲" : "▼"} {Math.abs(v).toFixed(1)}%</span>;
}
