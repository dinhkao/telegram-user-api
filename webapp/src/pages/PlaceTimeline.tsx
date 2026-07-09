// Timeline biến động 1 VỊ TRÍ KHO (#/vi-tri/:id/timeline) — tham khảo customer feed.
// CHỈ 2 loại: THÙNG VÀO / THÙNG RA. Thao tác trong cùng 5 phút gom 1 card. Bấm card
// (hoặc chip thùng) → lịch sử thao tác của thùng đó (#/thung/:id). RAIL phải: tồn kho
// chạy + CHẤM TRÒN bấm được → popup "kho lúc đó chứa gì" (tồn theo SP). Nhóm theo ngày
// + khe thời gian. Data: getPlaceTimeline.
import { useEffect, useRef, useState } from "preact/hooks";
import { getPlaceTimeline, soVN, type PlaceTLItem, type PlaceStockLine, type PlaceTimeline as PT } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
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
const sumQty = (ls: PlaceStockLine[]) => ls.reduce((s, l) => s + l.qty, 0);

// MỖI biến động = 1 DÒNG (giờ · Vào/Ra · SP·thùng · lý do). KHÔNG có chấm — chấm nằm
// ở JUNCTION giữa các biến động. Bấm dòng → lịch sử thao tác của thùng.
function EventRow({ it, idx }: { it: PlaceTLItem; idx: number }) {
  const inner = (
    <>
      <span class="pt-time">{hm(it.at)}</span>
      <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "Vào" : "Ra"}</span>
      <span class="pt-line-txt">{boxLabel(it)} <span class="muted">· {it.reason}</span></span>
    </>
  );
  // Bấm → chi tiết thùng + cuộn/nháy đúng thao tác đó trong Lịch sử (?focus=hist:<ts>)
  return (
    <li class="pt-item" id={`pev-${idx}`}>
      {it.box_id ? <a class="pt-line" href={`#/thung/${it.box_id}?focus=hist:${it.ts}`}>{inner}</a> : <div class="pt-line">{inner}</div>}
      <span class="pt-rail" />
    </li>
  );
}

// CHẤM TRẠNG THÁI ở giữa 2 biến động/cụm — bấm → kho tại thời điểm đó chứa gì. Khe cao
// TỈ LỆ thời gian (khi cách > 5 phút): chấm nằm CHÍNH GIỮA khe.
function Junction({ height, label, onDot }: { height: number; label: string | null; onDot: () => void }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">{label ? <span class="fg-label">· {label} ·</span> : null}</span>
      <span class="pt-rail"><button class="pt-dot" title="Xem kho lúc này chứa gì" onClick={onDot} /></span>
    </li>
  );
}

export function PlaceTimeline({ placeId, focus }: { placeId: string; focus?: string }) {
  const [d, setD] = useState<PT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [snap, setSnap] = useState<{ when: string; total: number; lines: PlaceStockLine[]; note?: string } | null>(null);
  usePopupBack(!!snap, () => setSnap(null));
  // Deep-link từ lịch sử thùng: ?focus=biendong:<ts> → cuộn + nháy biến động ts gần nhất
  const focusTs = focus?.startsWith("biendong-") ? Number(focus.slice(9)) : undefined;
  const focusedRef = useRef(false);
  useEffect(() => {
    if (!focusTs || !d?.items?.length || focusedRef.current) return;
    let best = -1, bestD = Infinity;
    d.items.forEach((it, i) => { const dd = Math.abs(it.ts - focusTs); if (dd < bestD) { bestD = dd; best = i; } });
    if (best < 0) return;
    focusedRef.current = true;
    const t = setTimeout(() => {
      const el = document.getElementById(`pev-${best}`);
      if (!el) return;
      fastScrollToEl(el, "center");
      el.classList.add("flash-target");
      setTimeout(() => el.classList.remove("flash-target"), 2400);
    }, 160);
    return () => clearTimeout(t);
  }, [d, focusTs]);

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
  const openState = (when: string, lines: PlaceStockLine[], note?: string) =>
    setSnap({ when, total: sumQty(lines), lines, note });

  // Trạng thái BAN ĐẦU (trước biến động cũ nhất) = state sau biến động cũ nhất, undo delta của nó
  let initLines: PlaceStockLine[] = [];
  if (items.length) {
    const li = items.length - 1, m = new Map(states[li]);
    m.set(items[li].product_code, (m.get(items[li].product_code) || 0) - items[li].delta);
    initLines = stateList(m);
  }

  // Xen kẽ: [ngày] [chấm trạng thái] [biến động] [chấm ...] … — chấm ở GIỮA các biến động
  const rows: any[] = [];
  if (items.length) {
    rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
    rows.push(<Junction key="j-top" height={0} label={null}
      onDot={() => openState(items[0].at, stateList(states[0]), "hiện tại")} />);
  }
  items.forEach((it, i) => {
    rows.push(<EventRow key={`e-${i}`} it={it} idx={i} />);
    const older = items[i + 1];
    if (older) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      // CHẤM chỉ ở RANH GIỚI 2 NHÓM (cách > 5 phút) — trong 1 cụm các dòng xếp sát, không chấm
      if (dsec > GROUP_SEC) {
        const gh = Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX));
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)}
          onDot={() => openState(older.at, stateList(states[i + 1]))} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    } else {
      rows.push(<Junction key="j-bot" height={0} label={null}
        onDot={() => openState(it.at, initLines, "trước biến động đầu")} />);
    }
  });

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
        <ul class="pt-list">{rows}</ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}

      {snap && (
        <div class="modal-overlay" onClick={() => setSnap(null)}>
          <div class="modal-sheet pt-snap" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="box" size={16} /> {d.place.name}{snap.note ? ` · ${snap.note}` : ""}</div>
            <div class="pt-snap-tot"><b>{soVN(snap.total)}</b> <span class="muted small">tồn · lúc {fmtDateTimeVN(snap.when)}</span></div>
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
