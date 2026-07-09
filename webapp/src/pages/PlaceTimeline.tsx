// Timeline biến động 1 VỊ TRÍ KHO (#/vi-tri/:id/timeline) — tham khảo customer feed.
// CHỈ 2 loại: THÙNG VÀO / THÙNG RA. Thao tác trong cùng 5 phút gom 1 card. Bấm card
// (hoặc chip thùng) → lịch sử thao tác của thùng đó (#/thung/:id). RAIL phải: tồn kho
// chạy + CHẤM TRÒN bấm được → popup "kho lúc đó chứa gì" (tồn theo SP). Nhóm theo ngày
// + khe thời gian. Data: getPlaceTimeline.
import { useEffect, useState } from "preact/hooks";
import { getPlaceTimeline, soVN, type PlaceTLItem, type PlaceStockLine, type PlaceTimeline as PT } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";

const GROUP_SEC = 300;   // gom thao tác trong vòng 5 phút vào 1 card
const hm = (v?: string) => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];
const gapDays = (a?: number, b?: number) => (a && b ? Math.round((a - b) / 86400) : 0);
const gapLabel = (d: number) =>
  d >= 60 ? `${Math.round(d / 30)} tháng` : d >= 14 ? `${Math.round(d / 7)} tuần` : `${d} ngày`;

type Card = {
  dir: "in" | "out"; idx: number; ts: number; at: string;
  entries: PlaceTLItem[]; net: number; total_after: number; state: PlaceStockLine[];
};

// Dựng lại tồn theo SP tại MỖI mốc: từ tồn hiện tại đi ngược thời gian (undo delta).
function buildStates(items: PlaceTLItem[], current: PlaceStockLine[]): Map<string, number>[] {
  const running = new Map<string, number>();
  for (const l of current) running.set(l.code, l.qty);
  const out: Map<string, number>[] = [];
  for (const it of items) {
    out.push(new Map(running));                 // trạng thái NGAY SAU mốc này
    const q = running.get(it.product_code) || 0;
    running.set(it.product_code, q - it.delta); // lùi 1 bước → trạng thái trước mốc
  }
  return out;
}

const stateList = (m: Map<string, number> | undefined): PlaceStockLine[] =>
  m ? [...m.entries()].filter(([, q]) => q > 0.0001).map(([code, qty]) => ({ code, qty: Math.round(qty * 1000) / 1000 }))
    .sort((a, b) => b.qty - a.qty) : [];

function buildCards(items: PlaceTLItem[], states: Map<string, number>[]): Card[] {
  const cards: Card[] = [];
  items.forEach((it, i) => {
    const last = cards[cards.length - 1];
    if (last && last.dir === it.dir && last.ts - it.ts <= GROUP_SEC) {
      last.entries.push(it); last.net += it.delta;
    } else {
      cards.push({ dir: it.dir, idx: i, ts: it.ts, at: it.at, entries: [it], net: it.delta,
                   total_after: it.total_after, state: stateList(states[i]) });
    }
  });
  return cards;
}

const boxLabel = (e: PlaceTLItem) => `${e.product_code} · ${e.box_num}`;

function CardRow({ c, onDot }: { c: Card; onDot: (c: Card) => void }) {
  const inn = c.dir === "in";
  const single = c.entries.length === 1;
  const title = <><b>Thùng {inn ? "vào" : "ra"}</b>{single ? "" : ` ×${c.entries.length}`}</>;
  const body = (
    <div class={"pt-card pt-" + c.dir}>
      <span class="fu-time">{hm(c.at)}</span>
      <div class="ultra-row">
        <span class={"pt-ic " + c.dir}><Icon name={inn ? "download" : "truck"} size={13} /></span>
        <span class="ultra-text">{title}
          {single ? <span class="muted"> · {boxLabel(c.entries[0])} · {c.entries[0].reason}</span> : null}
        </span>
      </div>
      {single ? (
        <div class="pt-sub muted">{c.entries[0].actor || "?"}</div>
      ) : (
        <div class="pt-boxes">
          {c.entries.map((e, i) => (
            <a class="pt-box-chip" key={i} href={e.box_id ? `#/thung/${e.box_id}` : undefined}
              title={`${boxLabel(e)} · ${e.reason}`}>{e.product_code} · {e.box_num}</a>
          ))}
        </div>
      )}
    </div>
  );
  return (
    <li class="pt-item">
      {single && c.entries[0].box_id
        ? <a class="pt-card-link" href={`#/thung/${c.entries[0].box_id}`}>{body}</a>
        : body}
      <span class="pt-rail">
        <button class={"pt-dot " + c.dir} title="Xem kho lúc này chứa gì" onClick={() => onDot(c)} />
        <span class={"pt-total " + (c.total_after > 0 ? "pos" : "zero")}>{soVN(c.total_after)}</span>
        <span class={"pt-delta " + c.dir}>{c.net > 0 ? "+" : "−"}{soVN(Math.abs(c.net))}</span>
      </span>
    </li>
  );
}

export function PlaceTimeline({ placeId }: { placeId: string }) {
  const [d, setD] = useState<PT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [snap, setSnap] = useState<{ when: string; total: number; lines: PlaceStockLine[] } | null>(null);
  usePopupBack(!!snap, () => setSnap(null));

  const load = () => {
    getPlaceTimeline(placeId)
      .then((r) => { if (!r) setErr("Không tìm thấy vị trí"); else setD(r); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải timeline"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [placeId]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed") {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [placeId]);

  if (loading && !d) return <Loading />;
  if (err || !d) return <ErrorState msg={err || "Không tìm thấy"} onRetry={load} />;

  const states = buildStates(d.items, d.current_by_product);
  const cards = buildCards(d.items, states);
  const openDot = (c: Card) => setSnap({ when: c.at, total: c.total_after, lines: c.state });

  return (
    <div class="place-tl">
      <div class="prod-detail-head">
        <BackLink fallback={`#/vi-tri/${d.place.id}`} />
        <div>
          <div class="prod-sp big"><Icon name="box" size={17} /> {d.place.name}</div>
          <div class="prod-date muted">Timeline biến động kho</div>
        </div>
      </div>

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (d.current_total > 0 ? "" : " zero")}>{soVN(d.current_total)}</div>
          <div class="muted small">tồn hiện tại · {d.box_count} thùng · {d.current_by_product.length} mã SP</div>
        </div>
        <span class="muted small">{cards.length} đợt{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {cards.length === 0 ? (
        <EmptyState>Kho này chưa có biến động nào được ghi.</EmptyState>
      ) : (
        <ul class="pt-list">
          {cards.flatMap((c, i) => {
            const nodes: any[] = [];
            const gd = i > 0 ? gapDays(cards[i - 1].ts, c.ts) : 0;
            if (gd >= 2) nodes.push(
              <li key={`g-${i}`} class="pt-gap" style={{ height: `${Math.min(gd * 12, 240)}px` }}>
                <span class="fg-label">· {gapLabel(gd)} ·</span>
              </li>);
            const day = dayKeyOf(c.at);
            if (i === 0 || dayKeyOf(cards[i - 1].at) !== day)
              nodes.push(<li key={`d-${day}-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(day)}</div></li>);
            nodes.push(<CardRow key={`${c.ts}-${i}`} c={c} onDot={openDot} />);
            return nodes;
          })}
        </ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {cards.length} đợt gần nhất.</div>}

      {snap && (
        <div class="modal-overlay" onClick={() => setSnap(null)}>
          <div class="modal-sheet pt-snap" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="box" size={16} /> {d.place.name} · {fmtDateTimeVN(snap.when)}</div>
            <div class="pt-snap-tot"><b>{soVN(snap.total)}</b> <span class="muted small">tồn lúc này</span></div>
            {snap.lines.length ? (
              <ul class="pt-snap-list">
                {snap.lines.map((l) => (
                  <li key={l.code}><b>{l.code}</b><span class="pt-snap-q">{soVN(l.qty)}</span></li>
                ))}
              </ul>
            ) : <p class="muted small">Kho trống lúc này.</p>}
            <button class="btn block" onClick={() => setSnap(null)}>Đóng</button>
          </div>
        </div>
      )}
    </div>
  );
}
