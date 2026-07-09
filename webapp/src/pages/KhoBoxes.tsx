// Kho hàng — MỌI thùng của MỌI sản phẩm, ô vuông trực quan. Tìm theo mã SP / SỐ
// THÙNG (số gọi) / vị trí. 2 chế độ xem: phẳng (mặc định) ↔ GOM THEO SP (toggle,
// nhớ lựa chọn). Tap ô → chi tiết thùng; tap header nhóm → chi tiết SP.
// Data: GET /api/inventory/boxes. Realtime: box/inventory/production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { allBoxes, soVN, type KhoBox } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";

// Nhớ filter + chế độ xem khi rời trang (module scope)
let memQ = "";
let memPlace = "";
let memGroup = false;

export function KhoBoxes() {
  const [boxes, setBoxes] = useState<KhoBox[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState(memQ);
  const [place, setPlace] = useState<string>(memPlace);   // "" = tất cả · tên vị trí · "__none"
  const [group, setGroup] = useState(memGroup);           // gom theo SP
  useEffect(() => { memQ = q; memPlace = place; memGroup = group; }, [q, place, group]);

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
  // Sắp: CÒN DÙNG ĐƯỢC (không vô hiệu + còn hàng) lên trước; trong mỗi nhóm,
  // MỚI TẠO lên trước (created_at giảm dần).
  const usable = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity) > 0 ? 1 : 0);
  const shown = boxes
    .filter((b) =>
      !nq ||
      foldVN(b.product_code).includes(nq) ||
      foldVN(b.box_code).includes(nq) ||          // số gọi thùng: gõ "347" ra thùng 347
      foldVN(b.place_name || "").includes(nq))
    .filter((b) => !place || (place === "__none" ? !b.place_name : b.place_name === place))
    .slice()
    .sort((a, b) =>
      usable(b) - usable(a) ||
      (b.created_at || "").localeCompare(a.created_at || "") ||
      b.box_code.localeCompare(a.box_code)
    );

  // Gom theo SP: giữ nguyên thứ tự thùng trong nhóm; nhóm sắp theo TỒN giảm dần rồi mã
  const rem = (b: KhoBox) => (b.disabled ? 0 : Math.max(0, b.remaining ?? b.quantity ?? 0));
  const groups = new Map<string, KhoBox[]>();
  if (group) {
    for (const b of shown) {
      const k = b.product_code || "?";
      const arr = groups.get(k);
      if (arr) arr.push(b); else groups.set(k, [b]);
    }
  }
  const sections = Array.from(groups.entries()).sort((a, b) => {
    const ta = a[1].reduce((s, x) => s + rem(x), 0);
    const tb = b[1].reduce((s, x) => s + rem(x), 0);
    return tb - ta || a[0].localeCompare(b[0]);
  });

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng <span class="muted small">({shown.length} thùng)</span></h2>
        <span class="row" style={{ gap: "6px" }}>
          <a class="btn small" href="#/vi-tri"><Icon name="box" size={15} /> Vị trí</a>
          <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
        </span>
      </div>
      <SearchBar value={q} onInput={setQ} placeholder="Tìm mã SP / số thùng / vị trí…" />
      <div class="place-chips">
        <button class={"chip" + (group ? " active" : "")} onClick={() => setGroup(!group)}>
          Gom theo SP
        </button>
        <button class={"chip" + (place === "" ? " active" : "")} onClick={() => setPlace("")}>Tất cả</button>
        {placeNames.map((p) => (
          <button key={p} class={"chip" + (place === p ? " active" : "")} onClick={() => setPlace(p)}>{p}</button>
        ))}
        {hasUnplaced && <button class={"chip" + (place === "__none" ? " active" : "")} onClick={() => setPlace("__none")}>Chưa xếp</button>}
      </div>

      {shown.length === 0 ? (
        <EmptyState>{boxes.length ? "Không có mã khớp." : "Kho trống. Nhập thùng ở phiếu SX."}</EmptyState>
      ) : group ? (
        <div class="kho-groups">
          {sections.map(([code, list]) => (
            <section class="kho-group" key={code}>
              <a class="kho-group-h" href={`#/kho/${encodeURIComponent(code)}`}>
                <b>{code}</b>
                <span class="muted small">
                  {soVN(list.reduce((s, x) => s + rem(x), 0))} tồn · {list.length} thùng →
                </span>
              </a>
              <BoxLabelGrid boxes={list} />
            </section>
          ))}
        </div>
      ) : (
        <BoxLabelGrid boxes={shown} />
      )}
    </div>
  );
}
