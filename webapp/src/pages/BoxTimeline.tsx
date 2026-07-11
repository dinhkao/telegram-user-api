// Timeline biến động 1 THÙNG (#/thung/:id/timeline). Đời của thùng: nhập mới → xuất
// cho đơn / thu về / chuyển kho / chuyển sang-nhận thùng khác, kèm TỒN thùng chạy
// (còn X→Y). Bố cục giống timeline kho (rail + chấm + giãn theo thời gian). Data: getBoxTimeline.
import { useEffect, useRef, useState } from "preact/hooks";
import { getBoxTimeline, soVN, type BoxTimeline as BT, type BoxTLItem } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { fastScrollToEl } from "../scroll";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";

const GROUP_SEC = 300;
const GAP_PXPS = 0.0333, GAP_MAX = 4000;
// Khe có chấm phải cao tối thiểu + kẹp lề khi trượt → số tồn không tràn đè dòng biến động.
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
const chip = (num?: string) => <span class="pt-bchip"><span class="pt-bn">{num}</span></span>;

function EventRow({ it, idx, srcSlip }: { it: BoxTLItem; idx: number; srcSlip?: number | null }) {
  const amt = it.amount;
  const u = it.unit ? " " + it.unit : "";
  const otxt = it.order_text ? (it.order_text.length > 34 ? it.order_text.slice(0, 34).trimEnd() + "…" : it.order_text) : "";
  const ord = it.order_thread_id
    ? <> đơn "<a class="pt-inl" href={`#/order/${it.order_thread_id}`}>{otxt || "#" + it.order_thread_id}</a>"</>
    : (otxt ? <> đơn "{otxt}"</> : null);
  const act = (() => {
    switch (it.kind) {
      case "created": return <>nhập mới <b>{soVN(amt)}</b>{u} từ {srcSlip ? <a class="pt-inl" href={`#/san_xuat/${srcSlip}`}>phiếu sản xuất</a> : "phiếu sản xuất"}</>;
      case "allocated": return <>xuất <b>{soVN(amt)}</b>{u} cho{ord}</>;
      case "released": return <>thu <b>{soVN(amt)}</b>{u} về từ{ord}</>;
      case "moved": return <>chuyển từ kho <b>{it.from_name || "?"}</b> → kho <b>{it.to_name || "?"}</b></>;
      case "transfer_out": return <>chuyển <b>{soVN(amt)}</b>{u} sang thùng {chip(it.peer_box)}{it.to_name ? <> ở <b>{it.to_name}</b></> : null}</>;
      case "transfer_in": return <>nhận <b>{soVN(amt)}</b>{u} từ thùng {chip(it.peer_box)}{it.from_name ? <> ở <b>{it.from_name}</b></> : null}</>;
      case "consumed": return <>tiêu hao <b>{soVN(amt)}</b>{u} để đóng gói <b class="pt-sp">{it.target_code}</b>{it.slip_id ? <> <a class="pt-inl" href={`#/san_xuat/${it.slip_id}`}>(phiếu SX)</a></> : null}</>;
      default: return <>{it.reason}</>;
    }
  })();
  return (
    <li class="pt-item" id={`bev-${idx}`}>
      <div class="pt-line">
        <span class="pt-time">{hm(it.at)}</span>
        <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : it.dir === "out" ? "−" : "•"}</span>
        <span class="pt-line-txt">
          {it.actor && it.actor !== "?" ? <><b class="pt-who">{it.actor}</b> </> : null}
          {act}
        </span>
      </div>
      <span class="pt-rail" />
    </li>
  );
}

function Junction({ height, label, amount }: { height: number; label: string | null; amount?: number | null }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">
        {label && <span class="pt-gaplbl pt-slide"><span class="fg-label">· {label} ·</span></span>}
      </span>
      <span class="pt-rail">
        <span class="pt-bead pt-slide">
          {amount != null && <span class="pt-dot-amt">{soVN(amount)}</span>}
          <span class="pt-dot pt-dot-static" />
        </span>
      </span>
    </li>
  );
}

export function BoxTimeline({ boxId }: { boxId: string }) {
  const [d, setD] = useState<BT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const focusedRef = useRef(false);
  const listRef = useRef<HTMLUListElement>(null);

  // Chấm tồn TRƯỢT theo cuộn (như hạt nợ ở feed khách): mỗi khe (junction) có 1 chấm
  // trượt trong phạm vi khe theo đường ghim ~45% màn hình. rAF khi đang cuộn.
  useEffect(() => {
    const apply = () => {
      const juncs = listRef.current?.querySelectorAll<HTMLElement>(".pt-junc");
      if (!juncs) return;
      const pin = window.innerHeight * 0.45;
      juncs.forEach((j) => {
        const r = j.getBoundingClientRect();
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
    const t = setTimeout(apply, 60);   // đặt vị trí ban đầu sau render
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); clearTimeout(t); };
  }, [d]);

  const load = () => {
    getBoxTimeline(boxId)
      .then((r) => { if (!r) setErr("Không tìm thấy thùng"); else setD(r); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải timeline"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [boxId]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed") {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [boxId]);
  useEffect(() => { focusedRef.current = false; }, [boxId]);

  if (loading && !d) return <Loading />;
  if (err || !d) return <ErrorState msg={err || "Không tìm thấy"} onRetry={load} />;

  const items = d.items;
  const src = d.box.source_thread_id;
  const rows: any[] = [];
  if (items.length) {
    rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
    rows.push(<Junction key="j-top" height={MIN_JUNC} label={null} amount={d.box.remaining} />);   // tồn HIỆN TẠI
  }
  items.forEach((it, i) => {
    rows.push(<EventRow key={`e-${i}`} it={it} idx={i} srcSlip={src} />);
    const older = items[i + 1];
    if (older) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      if (dsec > GROUP_SEC) {
        // cao tỉ lệ thời gian nhưng KHÔNG dưới MIN_JUNC → số tồn đủ chỗ, không đè dòng
        const gh = Math.max(MIN_JUNC, cross ? 0 : Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX)));
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)} amount={older.remaining} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    }
  });

  return (
    <div class="place-tl">
      <div class="prod-detail-head">
        <BackLink fallback={`#/thung/${d.box.id}`} />
        <div>
          <div class="prod-sp big"><Icon name="box" size={17} /> Thùng {d.box.box_num} · {d.box.product_code}</div>
          <div class="prod-date muted">Timeline biến động thùng</div>
        </div>
      </div>

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (d.box.remaining > 0 ? "" : " zero")}>{soVN(d.box.remaining)}</div>
          <div class="muted small">tồn hiện tại{d.box.place_name ? ` · ${d.box.place_name}` : ""} · {d.box.unit}</div>
        </div>
        <span class="muted small">{items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {items.length === 0 ? (
        <EmptyState>Thùng này chưa có biến động nào được ghi.</EmptyState>
      ) : (
        <ul class="pt-list" ref={listRef}>{rows}</ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}
    </div>
  );
}
