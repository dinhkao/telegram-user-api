// Khối hình dùng chung cho popup chi tiết ô bảng pivot lương SP (detail/WagePivotCell):
//   · CompBar     — thanh cấu thành tiền SP / tăng ca / phụ cấp (cùng 3 màu với khối
//                   tiền công phiếu SX — class .pwl-* của detail/ProductionWages),
//   · DayTimeline — trục giờ trong ngày, mỗi phiếu 1 khối, vùng TĂNG CA tô cam,
//   · RankBars    — danh sách so sánh có thanh ngang (thợ trong phiếu / trong ngày),
//   · LinkChips   — dải link sang trang liên quan.
import type { ComponentChildren } from "preact";
import { moneyR as money } from "../format";
import { Icon } from "../ui/Icon";
import { hm, tmin, type Comp } from "./wagePivotData";

const pct = (v: number, t: number) => (t > 0 ? `${Math.max(0, (v / t) * 100).toFixed(2)}%` : "0%");

export function CompBar({ c }: { c: Comp }) {
  const t = c.sp + c.tc + Math.max(0, c.pc);
  return (
    <div class="pwl wpc-comp">
      <div class="pwl-bar big">
        {c.sp > 0 && <i class="sp" style={`width:${pct(c.sp, t)}`} />}
        {c.tc > 0 && <i class="tc" style={`width:${pct(c.tc, t)}`} />}
        {c.pc > 0 && <i class="pc" style={`width:${pct(c.pc, t)}`} />}
      </div>
      <div class="pwl-legend">
        <span><i class="sp" /> Tiền SP <b>{money(c.sp)}đ</b></span>
        {c.tc ? <span><i class="tc" /> Tăng ca <b>{money(c.tc)}đ</b></span> : null}
        {c.pc ? <span><i class="pc" /> Phụ cấp <b>{money(c.pc)}đ</b></span> : null}
      </div>
    </div>
  );
}

export type TLBlock = { key: string | number; label: string; start: string; end: string; active?: boolean; ot?: boolean };

/** Xếp khối vào LÀN để khối chồng giờ nhau (nhiều phiếu song song) không đè lên nhau. */
function lanes(bs: { a: number; b: number }[]): number[] {
  const ends: number[] = [];
  return bs.map(({ a, b }) => {
    let i = ends.findIndex((e) => e <= a);
    if (i < 0) { i = ends.length; ends.push(b); } else ends[i] = b;
    return i;
  });
}

export function DayTimeline({ blocks, sunday, onPick }: {
  blocks: TLBlock[]; sunday: boolean; onPick?: (key: string | number) => void;
}) {
  const timed = blocks
    .map((b) => ({ ...b, a: tmin(b.start), b2: tmin(b.end) }))
    .filter((b) => b.a != null && b.b2 != null && (b.b2 as number) > (b.a as number))
    .sort((x, y) => (x.a as number) - (y.a as number));
  const untimed = blocks.filter((b) => !timed.some((t) => t.key === b.key));
  if (!timed.length) {
    return untimed.length ? <p class="muted small">Phiếu không ghi giờ bắt đầu/kết thúc.</p> : null;
  }
  const lo = Math.min(7 * 60, Math.floor(Math.min(...timed.map((t) => t.a as number)) / 60) * 60);
  const hi = Math.max(18 * 60, Math.ceil(Math.max(...timed.map((t) => t.b2 as number)) / 60) * 60);
  const span = hi - lo;
  const x = (m: number) => `${(((m - lo) / span) * 100).toFixed(2)}%`;
  const ln = lanes(timed.map((t) => ({ a: t.a as number, b: t.b2 as number })));
  const nLanes = Math.max(...ln) + 1;
  const otFrom = sunday ? lo : 17 * 60;
  const ticks: number[] = [];
  for (let m = lo; m <= hi; m += span > 9 * 60 ? 120 : 60) ticks.push(m);
  return (
    <div class="wpt">
      <div class="wpt-track" style={`height:${nLanes * 22 + 4}px`}>
        {otFrom < hi && <div class="wpt-ot" style={`left:${x(otFrom)};right:0`} title={sunday ? "Chủ nhật: cả ngày là tăng ca" : "Sau 17:00: giờ tăng ca"} />}
        {ticks.map((m) => <div key={m} class="wpt-grid" style={`left:${x(m)}`} />)}
        {timed.map((t, i) => (
          <button key={t.key} type="button"
            class={`wpt-blk${t.active ? " active" : ""}${t.ot ? " ot" : ""}${onPick ? "" : " static"}`}
            style={`left:${x(t.a as number)};width:${x(lo + (t.b2 as number) - (t.a as number))};top:${ln[i] * 22 + 2}px`}
            title={`${t.label} · ${hm(t.start)}–${hm(t.end)}`}
            onClick={onPick ? () => onPick(t.key) : undefined}>
            <span>{t.label}</span>
          </button>
        ))}
      </div>
      <div class="wpt-axis">
        {ticks.map((m) => <span key={m} style={`left:${x(m)}`}>{Math.floor(m / 60)}h</span>)}
      </div>
      {untimed.length ? <p class="muted small">Không ghi giờ: {untimed.map((u) => u.label).join(", ")}</p> : null}
    </div>
  );
}

export type RankRow = { key: string | number; name: string; value: number; sub?: string; active?: boolean };

export function RankBars({ rows, onPick }: { rows: RankRow[]; onPick?: (key: string | number) => void }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div class="wpr">
      {rows.map((r, i) => {
        const inner = (
          <>
            <span class="wpr-rank">{i + 1}</span>
            <span class="wpr-main">
              <span class="wpr-top"><span class="wpr-name">{r.name}</span><b>{money(r.value)}đ</b></span>
              <span class="wpr-bar"><i style={`width:${pct(r.value, max)}`} /></span>
              {r.sub ? <span class="wpr-sub">{r.sub}</span> : null}
            </span>
          </>
        );
        return onPick
          ? <button type="button" key={r.key} class={`wpr-row tappable${r.active ? " active" : ""}`} onClick={() => onPick(r.key)}>{inner}</button>
          : <div key={r.key} class={`wpr-row${r.active ? " active" : ""}`}>{inner}</div>;
      })}
    </div>
  );
}

export type LinkItem = { icon: string; label: string; href?: string; onClick?: () => void };

export function LinkChips({ items, onNavigate }: { items: LinkItem[]; onNavigate: () => void }) {
  return (
    <div class="wpc-links">
      {items.map((l) => l.href
        ? <a key={l.label} class="wpc-link" href={l.href} onClick={onNavigate}><Icon name={l.icon} size={14} /> {l.label}</a>
        : <button key={l.label} type="button" class="wpc-link" onClick={l.onClick}><Icon name={l.icon} size={14} /> {l.label}</button>)}
    </div>
  );
}

export function Section({ title, children, right }: { title: string; children: ComponentChildren; right?: ComponentChildren }) {
  return (
    <section class="wpc-sec">
      <div class="wpc-sec-h"><span>{title}</span>{right}</div>
      {children}
    </section>
  );
}
