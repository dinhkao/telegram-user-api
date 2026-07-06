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
  // Phẳng — MỌI thùng cạnh nhau (không gom nhóm). Sắp theo mã SP rồi mã thùng.
  const shown = (nq ? boxes.filter((b) => foldVN(b.product_code).includes(nq)) : boxes)
    .slice()
    .sort((a, b) => a.product_code.localeCompare(b.product_code) || a.box_code.localeCompare(b.box_code));

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng <span class="muted small">({shown.length} thùng)</span></h2>
        <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
      </div>
      <input class="inv-search" type="search" placeholder="Tìm mã sản phẩm…" value={q}
        onInput={(e: any) => setQ(e.target.value)} />

      {shown.length === 0 ? (
        <EmptyState>{boxes.length ? "Không có mã khớp." : "Kho trống. Nhập thùng ở phiếu SX."}</EmptyState>
      ) : (
        <div class="box-grid lbl-grid">
          {shown.map((b) => {
            const rm = b.remaining ?? b.quantity;
            const used = b.allocated ?? 0;
            const st = b.disabled ? "off" : used > 0 ? "alloc" : "in";
            const num = (b.box_code || "").split("-").pop() || b.box_code;
            const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
            return (
              <a key={b.id} class={`box-lbl ${st}`} href={`#/thung/${b.id}`}
                title={`${b.box_code} · ${soVN(rm)} cây · ${status}${b.note ? ` · ${b.note}` : ""}`}>
                {b.note && <span class="bl-dot" />}
                <span class="bl-code">{b.product_code}</span>
                <span class="bl-q">{soVN(rm)}</span>
                <span class="bl-num">{num}</span>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
