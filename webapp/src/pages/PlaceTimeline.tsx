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
// Khoảng cách dòng TỈ LỆ THUẬN thời gian thực — CHÍNH XÁC TỚI PHÚT: cao = giây × PXPS
// (~2px/phút → 1 giờ ≈ 120px, 1 ngày ≈ 2880px), kẹp trần GAP_MAX. Nhãn khi cách ≥ 2 phút.
const GAP_PXPS = 0.0333, GAP_MAX = 4000;
const hm = (v?: string) => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];
function gapLabel(sec: number): string {
  const d = sec / 86400;
  if (d >= 60) return `${Math.round(d / 30)} tháng`;
  if (d >= 14) return `${Math.round(d / 7)} tuần`;
  if (d >= 1) return `${Math.round(d)} ngày`;
  const h = sec / 3600;
  if (h >= 1) return `${Math.round(h)} giờ`;
  return `${Math.max(1, Math.round(sec / 60))} phút`;
}

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

const boxLabel = (e: PlaceTLItem) => `${e.product_code} · ${e.box_num}`;

// MỖI biến động = 1 DÒNG (giờ · Vào/Ra · SP·thùng · lý do) + 1 chấm trên rail.
// Bấm dòng → lịch sử thao tác của thùng; bấm chấm → kho lúc đó chứa gì.
function EventRow({ it, onDot }: { it: PlaceTLItem; onDot: () => void }) {
  const inn = it.dir === "in";
  const inner = (
    <>
      <span class="pt-time">{hm(it.at)}</span>
      <span class={"pt-tag " + it.dir}>{inn ? "Vào" : "Ra"}</span>
      <span class="pt-line-txt">{boxLabel(it)} <span class="muted">· {it.reason}</span></span>
    </>
  );
  return (
    <li class="pt-item">
      {it.box_id ? <a class="pt-line" href={`#/thung/${it.box_id}`}>{inner}</a> : <div class="pt-line">{inner}</div>}
      <span class="pt-rail">
        <button class={"pt-dot " + it.dir} title="Xem kho lúc này chứa gì" onClick={onDot} />
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
  const items = d.items;

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
        <span class="muted small">{items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {items.length === 0 ? (
        <EmptyState>Kho này chưa có biến động nào được ghi.</EmptyState>
      ) : (
        <ul class="pt-list">
          {items.flatMap((it, i) => {
            const nodes: any[] = [];
            // GOM: các biến động cách nhau ≤ 5 phút xếp SÁT (cùng 1 cụm, không khe).
            // Cách > 5 phút → chèn khe cao TỈ LỆ THUẬN thời gian thực + nhãn.
            const dsec = i > 0 ? Math.max(0, items[i - 1].ts - it.ts) : 0;
            if (i > 0 && dsec > GROUP_SEC) {
              const gh = Math.min(dsec * GAP_PXPS, GAP_MAX);
              nodes.push(
                <li key={`g-${i}`} class="pt-gap" style={{ height: `${Math.round(gh)}px` }}>
                  <span class="fg-label">· {gapLabel(dsec)} ·</span>
                </li>);
            }
            const day = dayKeyOf(it.at);
            if (i === 0 || dayKeyOf(items[i - 1].at) !== day)
              nodes.push(<li key={`d-${day}-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(day)}</div></li>);
            nodes.push(<EventRow key={`${it.ts}-${i}`} it={it}
              onDot={() => setSnap({ when: it.at, total: it.total_after, lines: stateList(states[i]) })} />);
            return nodes;
          })}
        </ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}

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
