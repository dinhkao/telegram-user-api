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
  const [place, setPlace] = useState<string>("");   // "" = tất cả · tên vị trí · "__none"

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
  // Các vị trí kho đang có (cho chip lọc)
  const placeNames = Array.from(new Set(boxes.map((b) => b.place_name).filter(Boolean))).sort() as string[];
  const hasUnplaced = boxes.some((b) => !b.place_name);
  // Phẳng — MỌI thùng cạnh nhau. Sắp: CÒN DÙNG ĐƯỢC (không vô hiệu + còn hàng)
  // lên trước; trong mỗi nhóm, MỚI TẠO lên trước (created_at giảm dần).
  const usable = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity) > 0 ? 1 : 0);
  const shown = boxes
    .filter((b) => !nq || foldVN(b.product_code).includes(nq) || foldVN(b.place_name || "").includes(nq))
    .filter((b) => !place || (place === "__none" ? !b.place_name : b.place_name === place))
    .slice()
    .sort((a, b) =>
      usable(b) - usable(a) ||
      (b.created_at || "").localeCompare(a.created_at || "") ||
      b.box_code.localeCompare(a.box_code)
    );

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng <span class="muted small">({shown.length} thùng)</span></h2>
        <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
      </div>
      <input class="inv-search" type="search" placeholder="Tìm mã sản phẩm / vị trí…" value={q}
        onInput={(e: any) => setQ(e.target.value)} />
      {(placeNames.length > 0 || hasUnplaced) && (
        <div class="place-chips">
          <button class={"chip" + (place === "" ? " active" : "")} onClick={() => setPlace("")}>Tất cả</button>
          {placeNames.map((p) => (
            <button key={p} class={"chip" + (place === p ? " active" : "")} onClick={() => setPlace(p)}>{p}</button>
          ))}
          {hasUnplaced && <button class={"chip" + (place === "__none" ? " active" : "")} onClick={() => setPlace("__none")}>Chưa xếp</button>}
        </div>
      )}

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
                {b.place_name && <span class="bl-place">{b.place_name}</span>}
                <span class="bl-code">{b.product_code}</span>
                <span class="bl-q">{soVN(rm)}</span>
                <span class="bl-num">{b.unit_name && b.unit_name !== "Thùng" ? `${b.unit_name} ` : ""}{num}</span>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
