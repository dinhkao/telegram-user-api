// Timeline biến động 1 VỊ TRÍ KHO (#/vi-tri/:id/timeline). Header (tồn hiện tại) +
// InvTimelineBody dùng chung (dòng biến động + chấm "kho lúc đó chứa gì"). Data: getPlaceTimeline.
import { useEffect, useState } from "preact/hooks";
import { getPlaceTimeline, soVN, type PlaceTimeline as PT } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState } from "../ui/states";
import { InvTimelineBody } from "../detail/InvTimeline";

export function PlaceTimeline({ placeId, focus }: { placeId: string; focus?: string }) {
  const [d, setD] = useState<PT | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    getPlaceTimeline(placeId)
      .then((r) => { if (!r) setErr("Không tìm thấy vị trí"); else { setD(r); setErr(""); } })
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

  return (
    <div class="place-tl">
      <PageHead fallback={`#/vi-tri/${d.place.id}`}
        title={<><Icon name="box" size={17} /> {d.place.name}</>}
        sub="Timeline biến động kho" />

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (d.current_total > 0 ? "" : " zero")}>{soVN(d.current_total)}</div>
          <div class="muted small">tồn hiện tại · {d.box_count} thùng · {d.current_by_product.length} mã SP</div>
        </div>
        <span class="muted small">{d.items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      <InvTimelineBody items={d.items} currentBoxes={d.current_boxes} currentTotal={d.current_total} snapTitle={d.place.name}
        emptyText="Kho này chưa có biến động nào được ghi." focus={focus} />
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {d.items.length} biến động gần nhất.</div>}
    </div>
  );
}
