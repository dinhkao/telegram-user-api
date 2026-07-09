// Dashboard KHO HÀNG (#/kho). MẶC ĐỊNH: mỗi VỊ TRÍ kho = 1 card (thumbnail ảnh mới
// nhất + mã SP kèm số lượng tồn tại vị trí đó) → tap mở chi tiết kho. KHI GÕ SEARCH:
// đổi sang lưới Ô THÙNG vuông, GOM THEO VỊ TRÍ. Data: listPlaces + allBoxes.
// Realtime: box/inventory/production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { listPlaces, allBoxes, mediaImageUrl, soVN, type Place, type KhoBox } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";

let memQ = "";                 // nhớ search khi rời trang
const MAX_CHIPS = 8;           // số mã SP hiện trên 1 card (còn lại gộp "+k")

// Tồn dùng được của 1 thùng (vô hiệu = 0)
const rem = (b: KhoBox) => (b.disabled ? 0 : Math.max(0, b.remaining ?? b.quantity ?? 0));
// Sắp ô thùng: còn dùng được lên trước, rồi mới tạo trước
const usable = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity) > 0 ? 1 : 0);
const sortBoxes = (a: KhoBox, b: KhoBox) =>
  usable(b) - usable(a) ||
  (b.created_at || "").localeCompare(a.created_at || "") ||
  a.box_code.localeCompare(b.box_code);

// Gộp mã SP + tổng tồn trong 1 nhóm thùng (tồn giảm dần)
function prodAgg(bs: KhoBox[]): { code: string; qty: number }[] {
  const m = new Map<string, number>();
  for (const b of bs) {
    const r = rem(b);
    if (r <= 0) continue;
    m.set(b.product_code, (m.get(b.product_code) || 0) + r);
  }
  return Array.from(m.entries())
    .map(([code, qty]) => ({ code, qty }))
    .sort((a, b) => b.qty - a.qty || a.code.localeCompare(b.code));
}

function ProdChips({ prods }: { prods: { code: string; qty: number }[] }) {
  if (!prods.length) return <div class="kho-loc-empty">Trống — chưa có hàng</div>;
  const head = prods.slice(0, MAX_CHIPS);
  const more = prods.length - head.length;
  return (
    <div class="kho-loc-prods">
      {head.map((p) => (
        <span class="kho-loc-prod" key={p.code}><b>{p.code}</b> {soVN(p.qty)}</span>
      ))}
      {more > 0 && <span class="kho-loc-prod more">+{more} mã</span>}
    </div>
  );
}

export function KhoBoxes() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [err, setErr] = useState("");
  const [q, setQ] = useState(memQ);
  const [openUnplaced, setOpenUnplaced] = useState(false);
  useEffect(() => { memQ = q; }, [q]);

  const load = async () => {
    try {
      const [pl, bx] = await Promise.all([listPlaces(), allBoxes()]);
      setPlaces(pl); setBoxes(bx);
    } catch (e: any) { setErr(e?.message || "Lỗi tải kho"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "resync" || e.type === "box_changed" || e.type === "inventory_changed" || e.type === "production_changed") load();
  }), []);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!places) return <Loading />;

  const nq = foldVN(q.trim());
  const searching = nq !== "";
  const unplaced = boxes.filter((b) => !b.place_id);
  const sortedPlaces = places.slice().sort((a, b) => a.name.localeCompare(b.name));

  const header = (
    <div class="row space">
      <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng{" "}
        <span class="muted small">({searching ? `${boxes.filter((b) => matchQ(b, nq)).length} thùng` : `${places.length} vị trí`})</span>
      </h2>
      <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
    </div>
  );
  const search = <SearchBar value={q} onInput={setQ} placeholder="Tìm mã SP / số thùng / vị trí…" />;

  // ── SEARCH: lưới ô thùng, GOM THEO VỊ TRÍ ────────────────────────────────
  if (searching) {
    const groups: { key: string; name: string; href?: string; list: KhoBox[] }[] = [];
    for (const p of sortedPlaces) {
      const list = boxes.filter((b) => b.place_id === p.id && matchQ(b, nq)).sort(sortBoxes);
      if (list.length) groups.push({ key: `p${p.id}`, name: p.name, href: `#/vi-tri/${p.id}`, list });
    }
    const un = unplaced.filter((b) => matchQ(b, nq)).sort(sortBoxes);
    if (un.length) groups.push({ key: "none", name: "Chưa xếp vị trí", list: un });

    return (
      <div class="inv-dash">
        {header}{search}
        {groups.length === 0 ? (
          <EmptyState>Không có thùng khớp “{q.trim()}”.</EmptyState>
        ) : (
          <div class="kho-groups">
            {groups.map((g) => (
              <section class="kho-group" key={g.key}>
                {g.href ? (
                  <a class="kho-group-h" href={g.href}>
                    <b><Icon name="box" size={15} /> {g.name}</b>
                    <span class="muted small">{soVN(g.list.reduce((s, x) => s + rem(x), 0))} tồn · {g.list.length} thùng →</span>
                  </a>
                ) : (
                  <div class="kho-group-h">
                    <b>{g.name}</b>
                    <span class="muted small">{soVN(g.list.reduce((s, x) => s + rem(x), 0))} tồn · {g.list.length} thùng</span>
                  </div>
                )}
                <BoxLabelGrid boxes={g.list} />
              </section>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── MẶC ĐỊNH: card từng vị trí kho ──────────────────────────────────────
  return (
    <div class="inv-dash">
      {header}{search}
      {places.length === 0 && unplaced.length === 0 ? (
        <EmptyState>Chưa có vị trí kho. Tạo ở <a href="#/vi-tri">Vị trí kho</a>.</EmptyState>
      ) : (
        <div class="kho-loc-list">
          {sortedPlaces.map((p) => {
            const bs = boxes.filter((b) => b.place_id === p.id);
            const total = bs.reduce((s, b) => s + rem(b), 0);
            return (
              <a class="kho-loc-card" href={`#/vi-tri/${p.id}`} key={p.id}>
                {p.thumb_image_id != null ? (
                  <img class="kho-loc-thumb" loading="lazy" alt=""
                    src={mediaImageUrl(`/api/media/place/${p.id}`, p.thumb_image_id, "thumb")} />
                ) : (
                  <div class="kho-loc-thumb ph"><Icon name="box" size={26} /></div>
                )}
                <div class="kho-loc-main">
                  <div class="kho-loc-head">
                    <span class="kho-loc-name"><Icon name="box" size={16} /> {p.name}</span>
                    <span class={"kho-loc-tot" + (total > 0 ? "" : " zero")}>{soVN(total)}<span class="muted small"> tồn · {bs.length} thùng</span></span>
                  </div>
                  <ProdChips prods={prodAgg(bs)} />
                </div>
                <Icon name="chevronRight" size={18} class="kg-arrow" />
              </a>
            );
          })}

          {unplaced.length > 0 && (
            <div class="kho-loc-card unplaced" onClick={() => setOpenUnplaced((v) => !v)}>
              <div class="kho-loc-thumb ph"><Icon name="box" size={26} /></div>
              <div class="kho-loc-main">
                <div class="kho-loc-head">
                  <span class="kho-loc-name muted">Chưa xếp vị trí</span>
                  <span class="kho-loc-tot">{soVN(unplaced.reduce((s, b) => s + rem(b), 0))}<span class="muted small"> tồn · {unplaced.length} thùng</span></span>
                </div>
                <ProdChips prods={prodAgg(unplaced)} />
              </div>
              <Icon name="chevronRight" size={18} class={"kg-arrow" + (openUnplaced ? " open" : "")} />
            </div>
          )}
          {openUnplaced && unplaced.length > 0 && (
            <div class="kho-unplaced-grid"><BoxLabelGrid boxes={unplaced.slice().sort(sortBoxes)} /></div>
          )}
        </div>
      )}
    </div>
  );
}

// Khớp tìm kiếm: mã SP / số gọi thùng / tên vị trí
function matchQ(b: KhoBox, nq: string): boolean {
  return foldVN(b.product_code).includes(nq)
    || foldVN(b.box_code).includes(nq)
    || foldVN(b.place_name || "").includes(nq);
}
