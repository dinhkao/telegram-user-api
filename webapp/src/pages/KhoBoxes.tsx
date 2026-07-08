// Kho hàng — MỌI thùng của MỌI sản phẩm, gom nhóm theo mã SP, hiện ô vuông trực
// quan. Ô lọc theo mã sản phẩm. Tap ô → chi tiết thùng; tap header → chi tiết SP.
// Data: GET /api/inventory/boxes. Realtime: box/inventory/production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { allBoxes, type KhoBox } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";

// Nhớ filter khi rời trang (module scope)
let memQ = "";
let memPlace = "";

export function KhoBoxes() {
  const [boxes, setBoxes] = useState<KhoBox[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState(memQ);
  const [place, setPlace] = useState<string>(memPlace);   // "" = tất cả · tên vị trí · "__none"
  useEffect(() => { memQ = q; memPlace = place; }, [q, place]);

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
        <span class="row" style={{ gap: "6px" }}>
          <a class="btn small" href="#/vi-tri"><Icon name="box" size={15} /> Vị trí</a>
          <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
        </span>
      </div>
      <SearchBar value={q} onInput={setQ} placeholder="Tìm mã sản phẩm / vị trí…" />
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
        <BoxLabelGrid boxes={shown} />
      )}
    </div>
  );
}
