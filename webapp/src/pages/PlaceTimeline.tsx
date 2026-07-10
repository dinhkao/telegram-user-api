// Timeline biến động 1 VỊ TRÍ KHO (#/vi-tri/:id/timeline) — tham khảo customer feed.
// CHỈ 2 loại: THÙNG VÀO / THÙNG RA. Thao tác trong cùng 5 phút gom 1 card. Bấm card
// (hoặc chip thùng) → lịch sử thao tác của thùng đó (#/thung/:id). RAIL phải: tồn kho
// chạy + CHẤM TRÒN bấm được → popup "kho lúc đó chứa gì" (tồn theo SP). Nhóm theo ngày
// + khe thời gian. Data: getPlaceTimeline.
import { useEffect, useRef, useState } from "preact/hooks";
import { getPlaceTimeline, soVN, type PlaceTLItem, type PlaceBox, type PlaceTimeline as PT } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";

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

const boxLabel = (e: PlaceTLItem) => `${e.product_code} · ${e.box_num}`;
const sumRem = (bs: PlaceBox[]) => bs.reduce((s, b) => s + Math.max(0, b.remaining), 0);

// Undo 1 biến động: đưa BỘ THÙNG từ trạng thái SAU mốc → TRƯỚC mốc (đi ngược thời gian).
// vào(created/moved_in) = thùng mới có mặt → gỡ; ra(moved_out/deleted) = thùng đã rời → thêm
// lại (remaining = phần đã rời = |delta|); còn lại chỉ đổi remaining (allocate/trả/chuyển hàng).
function undoEvent(m: Map<number, PlaceBox>, it: PlaceTLItem): void {
  const id = it.box_id;
  if (id == null) return;
  if (it.kind === "created" || it.kind === "moved_in") {
    m.delete(id);
  } else if (it.kind === "moved_out" || it.kind === "deleted") {
    const q = Math.abs(it.delta);
    m.set(id, { id, box_code: it.box_code || String(id), product_code: it.product_code,
      quantity: it.quantity ?? q, remaining: q, allocated: (it.quantity ?? q) - q,
      product_unit: "cây", disabled: false });
  } else {
    const b = m.get(id);
    if (b) { const rem = b.remaining - it.delta; m.set(id, { ...b, remaining: rem, allocated: b.quantity - rem }); }
  }
}

// Bộ thùng của kho NGAY SAU biến động thứ targetIdx (0 = hiện tại; n = trước biến động cũ nhất).
function boxesAt(items: PlaceTLItem[], current: PlaceBox[], targetIdx: number): PlaceBox[] {
  const m = new Map<number, PlaceBox>();
  for (const b of current) m.set(b.id, { ...b });
  for (let i = 0; i < targetIdx; i++) undoEvent(m, items[i]);   // gỡ các biến động MỚI hơn targetIdx
  return [...m.values()].filter((b) => b.remaining > 0.0001);
}

// Gom thùng theo mã SP (tồn giảm dần) cho popup grid
function groupByProduct(bs: PlaceBox[]): [string, PlaceBox[]][] {
  const g = new Map<string, PlaceBox[]>();
  for (const b of bs) { const a = g.get(b.product_code); if (a) a.push(b); else g.set(b.product_code, [b]); }
  return [...g.entries()].sort((a, b) => sumRem(b[1]) - sumRem(a[1]) || a[0].localeCompare(b[0]));
}

// MỖI biến động = 1 DÒNG (giờ · Vào/Ra · SP·thùng · lý do). KHÔNG có chấm — chấm nằm
// ở JUNCTION giữa các biến động. Bấm dòng → lịch sử thao tác của thùng.
function EventRow({ it, idx }: { it: PlaceTLItem; idx: number }) {
  const amt = it.amount ?? Math.abs(it.delta);
  const rem = it.remaining;                       // tồn thùng SAU biến động
  // Chuyển KHO: cả thùng đổi vị trí, số lượng KHÔNG đổi → không có before→after
  const isMove = it.kind === "moved_in" || it.kind === "moved_out";
  const before = rem != null && !isMove ? Math.round((it.dir === "out" ? rem + amt : rem - amt) * 1000) / 1000 : null;
  const chip = (num?: string) => <span class="pt-bchip"><span class="pt-bn">{num}</span></span>;
  // Cắt order text để "thùng còn…" (info sau) không bị clamp 2 dòng nuốt mất
  const otxt = it.order_text ? (it.order_text.length > 30 ? it.order_text.slice(0, 30).trimEnd() + "…" : it.order_text) : "";
  const ord = otxt ? <> · đơn "<span class="pt-otext">{otxt}</span>"</> : null;
  const u = it.unit ? " " + it.unit : "";   // đơn vị SP sau số lượng
  // Mô tả rõ: LÀM GÌ + bao nhiêu (+ đơn / thùng đích)
  const act = (() => {
    switch (it.kind) {
      case "allocated": return <>xuất <b>{soVN(amt)}</b>{u} cho{ord}</>;
      case "released": return <>trả <b>{soVN(amt)}</b>{u} về từ{ord}</>;
      case "created": return <>nhập mới <b>{soVN(amt)}</b>{u}</>;
      case "moved_in": return <>nhận <b>{soVN(amt)}</b>{u} chuyển từ kho <b>{it.from_name || "khác"}</b></>;
      case "moved_out": return <>chuyển <b>{soVN(amt)}</b>{u} sang kho <b>{it.to_name || "khác"}</b></>;
      case "deleted": return <>xoá thùng ({soVN(amt)}{u})</>;
      case "transfer_out": return <>chuyển <b>{soVN(amt)}</b>{u} sang thùng {chip(it.peer_box)}</>;
      case "transfer_in": return <>nhận <b>{soVN(amt)}</b>{u} từ thùng {chip(it.peer_box)}</>;
      default: return <>{it.reason}</>;
    }
  })();
  const inner = (
    <>
      <span class="pt-time">{hm(it.at)}</span>
      <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : "−"}</span>
      <span class="pt-line-txt">
        <b class="pt-sp">{it.product_code}</b> {chip(it.box_num)}{" "}
        {it.actor && it.actor !== "?" ? <><b class="pt-who">{it.actor}</b> </> : null}
        {act}
        {before != null ? <span class="muted"> · thùng còn <span class="pt-prog">{soVN(before)}→<b>{soVN(rem!)}</b></span></span>
          : isMove && rem != null ? <span class="muted"> · thùng còn <b class="pt-prog">{soVN(rem)}</b></span> : null}
      </span>
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
  const [snap, setSnap] = useState<{ when: string; boxes: PlaceBox[]; note?: string } | null>(null);
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

  const items = d.items;
  // Bấm chấm → dựng lại BỘ THÙNG của kho tại thời điểm đó (state sau biến động targetIdx)
  const openBoxes = (when: string, targetIdx: number, note?: string) =>
    setSnap({ when, boxes: boxesAt(items, d.current_boxes, targetIdx), note });

  // Xen kẽ: [ngày] [chấm trạng thái] [biến động] [chấm ...] … — chấm ở GIỮA các nhóm biến động
  const rows: any[] = [];
  if (items.length) {
    rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
    rows.push(<Junction key="j-top" height={0} label={null}
      onDot={() => openBoxes(items[0].at, 0, "hiện tại")} />);
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
          onDot={() => openBoxes(older.at, i + 1)} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    } else {
      rows.push(<Junction key="j-bot" height={0} label={null}
        onDot={() => openBoxes(it.at, items.length, "trước biến động đầu")} />);
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
            <div class="pt-snap-tot"><b>{soVN(sumRem(snap.boxes))}</b>
              <span class="muted small"> tồn · {snap.boxes.length} thùng · lúc {fmtDateTimeVN(snap.when)}</span></div>
            {snap.boxes.length ? (
              <div class="pt-snap-grid">
                {groupByProduct(snap.boxes).map(([code, bs]) => (
                  <section class="kho-group" key={code}>
                    <div class="kho-group-h"><b>{code}</b>
                      <span class="muted small">{soVN(sumRem(bs))} tồn · {bs.length} thùng</span></div>
                    <BoxLabelGrid boxes={bs as any} />
                  </section>
                ))}
              </div>
            ) : <p class="muted small">Kho trống lúc này.</p>}
            <button class="btn block" onClick={() => setSnap(null)}>Đóng</button>
          </div>
        </div>
      )}
    </div>
  );
}
