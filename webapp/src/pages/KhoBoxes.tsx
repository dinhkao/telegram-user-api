// Kho hàng — MỌI thùng của MỌI sản phẩm, gom nhóm theo mã SP, hiện ô vuông trực
// quan. Ô lọc theo mã sản phẩm. Tap ô → chi tiết thùng; tap header → chi tiết SP.
// Data: GET /api/inventory/boxes. Realtime: box/inventory/production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { allBoxes, soVN, type KhoBox } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";

export function KhoBoxes() {
  const [boxes, setBoxes] = useState<KhoBox[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");

  const load = async () => {
    try { setBoxes(await allBoxes()); } catch (e: any) { setErr(e?.message || "Lỗi tải kho"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(
    () => onRealtime((e) => {
      if (e.type === "resync" || e.type === "box_changed" || e.type === "inventory_changed" || e.type === "production_changed") load();
    }),
    []
  );

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!boxes) return <Loading />;

  const nq = foldVN(q.trim());
  const shown = nq ? boxes.filter((b) => foldVN(b.product_code).includes(nq)) : boxes;

  // Gom theo mã SP
  const groups: Record<string, KhoBox[]> = {};
  for (const b of shown) (groups[b.product_code] ||= []).push(b);
  const codes = Object.keys(groups).sort();

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng <span class="muted small">({shown.length} thùng)</span></h2>
        <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
      </div>
      <input class="inv-search" type="search" placeholder="Tìm mã sản phẩm…" value={q}
        onInput={(e: any) => setQ(e.target.value)} />

      {codes.length === 0 ? (
        <EmptyState>{boxes.length ? "Không có mã khớp." : "Kho trống. Nhập thùng ở phiếu SX (🏭 SX)."}</EmptyState>
      ) : (
        codes.map((code) => {
          const bs = groups[code];
          const rem = bs.reduce((s, b) => s + (b.disabled ? 0 : b.remaining), 0);
          return (
            <section class="kho-group" key={code}>
              <a class="kho-group-head" href={`#/kho/${encodeURIComponent(code)}`}>
                <span class="kg-code">{code}</span>
                <span class="kg-stat"><b>{soVN(rem)}</b> tồn · {bs.length} thùng</span>
                <Icon name="chevronRight" size={16} class="kg-arrow" />
              </a>
              <div class="box-grid">
                {bs.map((b) => {
                  const rm = b.remaining ?? b.quantity;
                  const used = b.allocated ?? 0;
                  const st = b.disabled ? "off" : used > 0 ? "alloc" : "in";
                  const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
                  return (
                    <a key={b.id} class={`box-sq ${st}`} href={`#/thung/${b.id}`}
                      title={`${b.box_code} · ${soVN(rm)} cây · ${status}${b.note ? ` · ${b.note}` : ""}`}>
                      {b.note && <span class="bs-dot" />}
                      <span class="bs-q">{soVN(rm)}</span>
                      <span class="bs-code">{b.box_code}</span>
                    </a>
                  );
                })}
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
