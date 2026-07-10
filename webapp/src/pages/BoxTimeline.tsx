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
  const rem = it.remaining;
  const before = rem != null ? Math.round((rem - it.delta) * 1000) / 1000 : null;
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
      default: return <>{it.reason}</>;
    }
  })();
  const noChange = it.delta === 0;
  const ton = noChange
    ? (rem != null ? <span class="pt-ton">còn <b class="pt-prog">{soVN(rem)}</b></span> : null)
    : (before != null ? <span class="pt-ton">còn <span class="pt-prog">{soVN(before)}→<b>{soVN(rem!)}</b></span></span> : null);
  return (
    <li class="pt-item" id={`bev-${idx}`}>
      <div class="pt-line">
        <span class="pt-time">{hm(it.at)}</span>
        <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : it.dir === "out" ? "−" : "•"}</span>
        <span class="pt-line-txt">
          {it.actor && it.actor !== "?" ? <><b class="pt-who">{it.actor}</b> </> : null}
          {act}
        </span>
        {ton}
      </div>
      <span class="pt-rail" />
    </li>
  );
}

function Junction({ height, label }: { height: number; label: string | null }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">{label ? <span class="fg-label">· {label} ·</span> : null}</span>
      <span class="pt-rail"><span class="pt-dot pt-dot-static" /></span>
    </li>
  );
}

export function BoxTimeline({ boxId }: { boxId: string }) {
  const [d, setD] = useState<BT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const focusedRef = useRef(false);

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
  }
  items.forEach((it, i) => {
    rows.push(<EventRow key={`e-${i}`} it={it} idx={i} srcSlip={src} />);
    const older = items[i + 1];
    if (older) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      if (dsec > GROUP_SEC) {
        const gh = Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX));
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)} />);
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
        <ul class="pt-list">{rows}</ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}
    </div>
  );
}
