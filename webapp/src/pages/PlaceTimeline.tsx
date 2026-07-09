// Timeline biến động 1 VỊ TRÍ KHO (#/vi-tri/:id/timeline) — tham khảo customer feed.
// Dòng thời gian nhập/xuất/chuyển/xoá của kho + RAIL TỒN CHẠY bên phải (số tồn sau
// mỗi biến động, giống rail nợ). Nhóm theo ngày + khe thời gian. Data: getPlaceTimeline.
import { useEffect, useState } from "preact/hooks";
import { getPlaceTimeline, soVN, type PlaceTLItem, type PlaceTimeline as PT } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";

const hm = (v?: string) => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];
const gapDays = (a?: number, b?: number) => (a && b ? Math.round((a - b) / 86400) : 0);
const gapLabel = (d: number) =>
  d >= 60 ? `${Math.round(d / 30)} tháng` : d >= 14 ? `${Math.round(d / 7)} tuần` : `${d} ngày`;

const KIND_ICON: Record<string, string> = {
  created: "box", allocated: "truck", released: "refresh", moved_in: "truck",
  moved_out: "truck", deleted: "trash", transfer_in: "truck", transfer_out: "truck",
};

function Row({ it }: { it: PlaceTLItem }) {
  const up = it.delta > 1e-9, down = it.delta < -1e-9;
  const deltaStr = up || down ? `${up ? "+" : "−"}${soVN(Math.abs(it.delta))}` : "";
  const dir = up ? "in" : down ? "out" : "";
  const card = (
    <div class={`order-card ultra pt-card pt-${it.kind}`}>
      <span class="fu-time">{hm(it.at)}</span>
      <div class="ultra-row">
        <span class={"pt-ic " + dir}><Icon name={KIND_ICON[it.kind] || "box"} size={13} /></span>
        <span class="ultra-text"><b>{it.action}</b>{it.detail ? <span class="muted"> · {it.detail}</span> : null}</span>
      </div>
      <div class="pt-sub muted">{it.actor || "?"}</div>
    </div>
  );
  return (
    <li class="pt-item">
      {it.order_thread_id ? <a class="pt-link" href={`#/order/${it.order_thread_id}`}>{card}</a> : card}
      <span class="pt-rail">
        <span class={"pt-dot " + dir} />
        <span class={"pt-total " + (it.total_after > 0 ? "pos" : "zero")}>{soVN(it.total_after)}</span>
        {deltaStr && <span class={"pt-delta " + dir}>{deltaStr}</span>}
      </span>
    </li>
  );
}

export function PlaceTimeline({ placeId }: { placeId: string }) {
  const [d, setD] = useState<PT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

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
          <div class="pt-head-tot"><span class={"pt-total-big" + (d.current_total > 0 ? "" : " zero")}>{soVN(d.current_total)}</span></div>
          <div class="muted small">tồn hiện tại · {d.box_count} thùng</div>
        </div>
        <span class="muted small">{items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {items.length === 0 ? (
        <EmptyState>Kho này chưa có biến động nào được ghi.</EmptyState>
      ) : (
        <ul class="pt-list">
          {items.flatMap((it, i) => {
            const nodes: any[] = [];
            const gd = i > 0 ? gapDays(items[i - 1].ts, it.ts) : 0;
            if (gd >= 2) nodes.push(
              <li key={`g-${i}`} class="pt-gap" style={{ height: `${Math.min(gd * 12, 240)}px` }}>
                <span class="fg-label">· {gapLabel(gd)} ·</span>
              </li>);
            const day = dayKeyOf(it.at);
            if (i === 0 || dayKeyOf(items[i - 1].at) !== day)
              nodes.push(<li key={`d-${day}-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(day)}</div></li>);
            nodes.push(<Row key={`${it.ts}-${it.kind}-${i}`} it={it} />);
            return nodes;
          })}
        </ul>
      )}
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}
    </div>
  );
}
