// Timeline biến động TỒN 1 SẢN PHẨM (#/kho/:code/timeline). Gộp mọi thùng của SP:
// sản xuất nhập / xuất đơn / thu về / tiêu hao đóng gói. Header (tồn hiện tại + kho chứa)
// + InvTimelineBody dùng chung (dòng biến động + chấm "SP lúc đó nằm ở thùng nào").
// Data: getProductTimeline. Vào từ chi tiết SP (#/kho/:code).
import { useEffect, useState } from "preact/hooks";
import { getProductTimeline, soVN, type ProductTimeline as PTL } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, ErrorState } from "../ui/states";
import { InvTimelineBody } from "../detail/InvTimeline";

export function ProductTimeline({ code, focus }: { code: string; focus?: string }) {
  const [d, setD] = useState<PTL | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    getProductTimeline(code)
      .then((r) => { if (!r) setErr("Không tìm thấy sản phẩm"); else setD(r); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải timeline"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [code]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed") {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [code]);

  if (loading && !d) return <Loading />;
  if (err || !d) return <ErrorState msg={err || "Không tìm thấy"} onRetry={load} />;

  const p = d.product;
  const below = p.min_stock > 0 && d.current_total < p.min_stock;
  return (
    <div class="place-tl">
      <div class="prod-detail-head">
        <BackLink fallback={`#/kho/${encodeURIComponent(p.code)}`} />
        <div>
          <div class="prod-sp big"><Icon name="box" size={17} /> {p.code}{p.name ? <span class="muted"> · {p.name}</span> : null}</div>
          <div class="prod-date muted">Timeline biến động tồn</div>
        </div>
      </div>

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (d.current_total > 0 ? "" : " zero")}>{soVN(d.current_total)}</div>
          <div class="muted small">
            tồn hiện tại {p.unit} · {d.box_count} thùng · {d.current_by_place.length} kho
            {p.min_stock > 0 && <> · tối thiểu {soVN(p.min_stock)}{below ? <b class="pt-below"> · DƯỚI MỨC</b> : null}</>}
          </div>
        </div>
        <span class="muted small">{d.items.length} biến động{d.truncated ? " (mới nhất)" : ""}</span>
      </div>

      {d.current_by_place.length > 0 && (
        <div class="pt-places">
          {d.current_by_place.map((x) => (
            <span class="pt-place-chip" key={x.place}>{x.place} <b>{soVN(x.qty)}</b></span>
          ))}
        </div>
      )}

      <InvTimelineBody items={d.items} currentBoxes={d.current_boxes} currentTotal={d.current_total} snapTitle={p.code}
        emptyText="Sản phẩm này chưa có biến động kho nào được ghi." focus={focus} />
      {d.truncated && <div class="muted small pt-trunc">Chỉ hiện {d.items.length} biến động gần nhất.</div>}
    </div>
  );
}
