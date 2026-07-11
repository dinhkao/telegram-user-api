// Phần render DÙNG CHUNG cho timeline biến động kho (vị trí + sản phẩm). Mỗi biến động =
// 1 dòng (giờ · +/− · actor · mô tả · tồn thùng chạy), CHẤM junction giãn theo thời gian →
// popup "lúc đó có những thùng nào" (dựng ngược từ bộ thùng hiện tại). Nhóm theo ngày.
// Dùng bởi pages/PlaceTimeline + pages/ProductTimeline. Data: PlaceTLItem[] + PlaceBox[].
import { useEffect, useRef, useState } from "preact/hooks";
import { soVN, type PlaceTLItem, type PlaceBox } from "../api";
import { fmtDateTimeVN } from "../format";
import { fastScrollToEl } from "../scroll";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { EmptyState } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "./OrderCards";
import { BoxLabelGrid } from "./BoxLabelGrid";

const GROUP_SEC = 300;   // gom thao tác trong vòng 5 phút vào 1 cụm
// Khoảng cách dòng TỈ LỆ thời gian: cao = giây × PXPS (~2px/phút), kẹp trần GAP_MAX.
const GAP_PXPS = 0.0333, GAP_MAX = 4000;
// Khe CÓ chấm/nhãn phải cao tối thiểu để nhãn không tràn đè dòng biến động; SLIDE_M =
// lề trên/dưới khi chấm trượt (nửa chiều cao nhãn) → chấm luôn nằm GỌN trong khe.
const MIN_JUNC = 34, SLIDE_M = 15;
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
const sumRem = (bs: PlaceBox[]) => bs.reduce((s, b) => s + Math.max(0, b.remaining), 0);

// Undo 1 biến động: đưa BỘ THÙNG từ trạng thái SAU mốc → TRƯỚC mốc (đi ngược thời gian).
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

// Bộ thùng NGAY SAU biến động thứ targetIdx (0 = hiện tại; n = trước biến động cũ nhất).
function boxesAt(items: PlaceTLItem[], current: PlaceBox[], targetIdx: number): PlaceBox[] {
  const m = new Map<number, PlaceBox>();
  for (const b of current) m.set(b.id, { ...b });
  for (let i = 0; i < targetIdx; i++) undoEvent(m, items[i]);
  return [...m.values()].filter((b) => b.remaining > 0.0001);
}

function groupByProduct(bs: PlaceBox[]): [string, PlaceBox[]][] {
  const g = new Map<string, PlaceBox[]>();
  for (const b of bs) { const a = g.get(b.product_code); if (a) a.push(b); else g.set(b.product_code, [b]); }
  return [...g.entries()].sort((a, b) => sumRem(b[1]) - sumRem(a[1]) || a[0].localeCompare(b[0]));
}

// MỖI biến động = 1 DÒNG. Bấm dòng → lịch sử thao tác của thùng (?focus=hist:<ts>).
function EventRow({ it, idx }: { it: PlaceTLItem; idx: number }) {
  const amt = it.amount ?? Math.abs(it.delta);
  const chip = (num?: string) => <span class="pt-bchip"><span class="pt-bn">{num}</span></span>;
  const otxt = it.order_text ? (it.order_text.length > 30 ? it.order_text.slice(0, 30).trimEnd() + "…" : it.order_text) : "";
  const ord = otxt ? <> đơn "<span class="pt-otext">{otxt}</span>"</> : null;
  const u = it.unit ? " " + it.unit : "";
  const boxRef = <>thùng <b class="pt-sp">{it.product_code}</b> {chip(it.box_num)}</>;
  const peer = <>thùng <b class="pt-sp">{it.product_code}</b> {chip(it.peer_box)}</>;
  const act = (() => {
    switch (it.kind) {
      case "allocated": return <>xuất <b>{soVN(amt)}</b>{u} từ {boxRef} cho{ord}</>;
      case "released": return <>trả <b>{soVN(amt)}</b>{u} về {boxRef} từ{ord}</>;
      case "created": return <>nhập mới {boxRef} <b>{soVN(amt)}</b>{u} từ phiếu sản xuất</>;
      case "moved_in": return <>chuyển {boxRef} từ kho <b>{it.from_name || "khác"}</b> đến đây</>;
      case "moved_out": return <>chuyển {boxRef} từ đây sang kho <b>{it.to_name || "khác"}</b></>;
      case "deleted": return <>xoá {boxRef} ({soVN(amt)}{u})</>;
      case "transfer_out": return <>đã chuyển <b>{soVN(amt)}</b>{u} từ {boxRef} sang {peer}{it.to_name ? <> ở <b>{it.to_name}</b></> : null}</>;
      case "transfer_in": return <>đã chuyển <b>{soVN(amt)}</b>{u} từ {peer}{it.from_name ? <> ở <b>{it.from_name}</b></> : null} sang {boxRef}</>;
      case "consumed": return <>tiêu hao <b>{soVN(amt)}</b>{u} từ {boxRef} để đóng gói <b class="pt-sp">{it.target_code}</b>{it.slip_id ? <> <a class="pt-inl" href={`#/san_xuat/${it.slip_id}`}>(phiếu SX)</a></> : null}</>;
      default: return <>{boxRef} {it.reason}</>;
    }
  })();
  const inner = (
    <>
      <span class="pt-time">{hm(it.at)}</span>
      <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : "−"}</span>
      <span class="pt-line-txt">
        {it.actor && it.actor !== "?" ? <><b class="pt-who">{it.actor}</b> </> : null}
        {act}
      </span>
    </>
  );
  return (
    <li class="pt-item" id={`pev-${idx}`}>
      {it.box_id ? <a class="pt-line" href={`#/thung/${it.box_id}?focus=hist:${it.ts}`}>{inner}</a> : <div class="pt-line">{inner}</div>}
      <span class="pt-rail" />
    </li>
  );
}

// CHẤM ở giữa 2 biến động: hiện SỐ TỒN tại thời điểm đó (trượt theo cuộn) + bấm → xem
// lúc đó có những thùng nào. Khe cao tỉ lệ thời gian.
function Junction({ height, label, amount, onDot }: { height: number; label: string | null; amount?: number | null; onDot: () => void }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">
        {label && <span class="pt-gaplbl pt-slide"><span class="fg-label">· {label} ·</span></span>}
      </span>
      <span class="pt-rail">
        <span class="pt-bead pt-slide">
          {amount != null && <span class="pt-dot-amt">{soVN(amount)}</span>}
          <button class="pt-dot" title="Xem lúc này có những thùng nào" onClick={onDot} />
        </span>
      </span>
    </li>
  );
}

// snapTitle = tên hiện ở popup (tên kho / mã SP). emptyText = câu khi chưa có biến động.
// currentTotal = tồn hiện tại (số ở chấm trên cùng).
export function InvTimelineBody({ items, currentBoxes, currentTotal, snapTitle, emptyText, focus }: {
  items: PlaceTLItem[]; currentBoxes: PlaceBox[]; currentTotal: number; snapTitle: string; emptyText: string; focus?: string;
}) {
  const [snap, setSnap] = useState<{ when: string; boxes: PlaceBox[]; note?: string } | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  usePopupBack(!!snap, () => setSnap(null));

  // Chấm tồn TRƯỢT theo cuộn (giống timeline thùng): mỗi khe có 1 chấm trượt trong phạm
  // vi khe theo đường ghim ~45% màn hình. rAF khi đang cuộn.
  useEffect(() => {
    const apply = () => {
      const juncs = listRef.current?.querySelectorAll<HTMLElement>(".pt-junc");
      if (!juncs) return;
      const pin = window.innerHeight * 0.45;
      juncs.forEach((j) => {
        const r = j.getBoundingClientRect();
        // kẹp trong [SLIDE_M, height−SLIDE_M] → chấm/nhãn không tràn ra dòng biến động;
        // khe quá ngắn (≤ 2·lề) → đặt giữa.
        const off = r.height <= SLIDE_M * 2 ? r.height / 2 : Math.min(Math.max(pin - r.top, SLIDE_M), r.height - SLIDE_M);
        j.querySelectorAll<HTMLElement>(".pt-slide").forEach((el) => { el.style.top = `${off}px`; });
      });
    };
    let raf = 0, running = false, lastY = -1, idle = 0;
    const tick = () => {
      const y = window.scrollY;
      if (y !== lastY) { lastY = y; idle = 0; apply(); }
      else if (++idle > 20) { running = false; return; }
      raf = requestAnimationFrame(tick);
    };
    const onScroll = () => { if (!running) { running = true; idle = 0; raf = requestAnimationFrame(tick); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    const t = setTimeout(apply, 60);
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); clearTimeout(t); };
  }, [items]);
  // Deep-link từ lịch sử thùng: ?focus=biendong-<ts> → cuộn + nháy biến động gần nhất
  const focusTs = focus?.startsWith("biendong-") ? Number(focus.slice(9)) : undefined;
  const focusedRef = useRef(false);
  useEffect(() => {
    if (!focusTs || !items.length || focusedRef.current) return;
    let best = -1, bestD = Infinity;
    items.forEach((it, i) => { const dd = Math.abs(it.ts - focusTs); if (dd < bestD) { bestD = dd; best = i; } });
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
  }, [items, focusTs]);

  if (items.length === 0) return <EmptyState>{emptyText}</EmptyState>;

  const openBoxes = (when: string, targetIdx: number, note?: string) =>
    setSnap({ when, boxes: boxesAt(items, currentBoxes, targetIdx), note });

  const rows: any[] = [];
  rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
  rows.push(<Junction key="j-top" height={MIN_JUNC} label={null} amount={currentTotal} onDot={() => openBoxes(items[0].at, 0, "hiện tại")} />);
  items.forEach((it, i) => {
    rows.push(<EventRow key={`e-${i}`} it={it} idx={i} />);
    const older = items[i + 1];
    if (older) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      if (dsec > GROUP_SEC) {
        // cao tỉ lệ thời gian nhưng KHÔNG dưới MIN_JUNC (đủ chỗ cho nhãn, không đè dòng)
        const gh = Math.max(MIN_JUNC, cross ? 0 : Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX)));
        // tồn tại khe này = tổng SAU biến động cũ hơn (giữ nguyên tới biến động mới hơn)
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)} amount={older.total_after} onDot={() => openBoxes(older.at, i + 1)} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    } else {
      // chấm cuối = tồn TRƯỚC biến động đầu tiên (tổng sau nó trừ đi delta của nó)
      rows.push(<Junction key="j-bot" height={MIN_JUNC} label={null} amount={Math.round((it.total_after - it.delta) * 1000) / 1000} onDot={() => openBoxes(it.at, items.length, "trước biến động đầu")} />);
    }
  });

  return (
    <>
      <ul class="pt-list" ref={listRef}>{rows}</ul>
      {snap && (
        <div class="modal-overlay" onClick={() => setSnap(null)}>
          <div class="modal-sheet pt-snap" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="box" size={16} /> {snapTitle}{snap.note ? ` · ${snap.note}` : ""}</div>
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
            ) : <p class="muted small">Trống lúc này.</p>}
            <button class="btn block" onClick={() => setSnap(null)}>Đóng</button>
          </div>
        </div>
      )}
    </>
  );
}
