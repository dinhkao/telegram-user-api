// Dashboard vị trí kho — mỗi Kho (A/B…) 1 card: số thùng + tồn. Tap → chi tiết kho.
// Tạo vị trí mới ngay đây. Data: listPlaces + allBoxes (gộp thống kê). Realtime reload.
import { useEffect, useState } from "preact/hooks";
import { listPlaces, allBoxes, createPlace, mediaImageUrl, soVN, type Place, type KhoBox } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";

export function PlacesList() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");   // lọc HIỂN THỊ theo tên vị trí (client-side)
  const [nName, setNName] = useState("");
  const [adding, setAdding] = useState(false);

  const load = async () => {
    try {
      const [pl, bx] = await Promise.all([listPlaces(), allBoxes()]);
      setPlaces(pl); setBoxes(bx);
    } catch (e: any) { setErr(e?.message || "Lỗi tải vị trí"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed") load();
  }), []);

  const doAdd = async () => {
    const name = nName.trim();
    if (!name) return;
    setAdding(true);
    try { await createPlace(name); setNName(""); await load(); toast(`✅ Tạo ${name}`, "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi tạo", "err"); }
    finally { setAdding(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!places) return <Loading />;

  const hasStock = (b: KhoBox) => (b.remaining ?? b.quantity ?? 0) > 0;   // thùng còn hàng
  const stat = (pid: number) => {
    const bs = boxes.filter((b) => b.place_id === pid);
    const rem = bs.reduce((s, b) => s + (b.disabled ? 0 : b.remaining), 0);
    return { count: bs.filter(hasStock).length, rem };   // đếm chỉ thùng còn hàng (rỗng đã ẩn)
  };
  const unplaced = boxes.filter((b) => !b.place_id && hasStock(b)).length;
  const nq = foldVN(q.trim());
  const shown = nq ? places.filter((p) => foldVN(p.name).includes(nq)) : places;

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Vị trí kho <span class="muted small">({places.length})</span></h2>
        <a class="btn small" href="#/kho"><Icon name="box" size={15} /> Tất cả thùng</a>
      </div>

      <div class="row" style={{ gap: "6px", marginBottom: "6px" }}>
        <input class="inv-search" style={{ flex: 1 }} placeholder="Tên vị trí mới (vd Kho C)" value={nName}
          onInput={(e: any) => setNName(e.target.value)} onKeyDown={(e: any) => { if (e.key === "Enter") doAdd(); }} />
        <button class="btn primary" disabled={adding || !nName.trim()} onClick={doAdd}><Icon name="plus" size={16} /></button>
      </div>
      <SearchBar value={q} onInput={setQ} placeholder="Tìm tên vị trí…" />

      {places.length === 0 ? (
        <EmptyState>Chưa có vị trí. Tạo Kho A, Kho B… ở trên.</EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState>Không có vị trí khớp “{q.trim()}”.</EmptyState>
      ) : (
        shown.map((p) => {
          const s = stat(p.id);
          return (
            <a class="inv-card" href={`#/vi-tri/${p.id}`} key={p.id}>
              {p.thumb_image_id != null && (
                <img class="place-thumb" loading="lazy" alt=""
                  src={mediaImageUrl(`/api/media/place/${p.id}`, p.thumb_image_id, "thumb")} />
              )}
              <div class="inv-card-main">
                <div class="inv-card-code"><Icon name="box" size={15} /> {p.name}</div>
                {p.note ? <div class="inv-card-name muted small">{p.note}</div> : null}
              </div>
              <div class="inv-card-stat">
                <span class={"inv-card-total" + (s.rem > 0 ? "" : " zero")}>{soVN(s.rem)}</span>
                <span class="muted small">tồn · {s.count} thùng</span>
              </div>
              <Icon name="chevronRight" size={18} class="kg-arrow" />
            </a>
          );
        })
      )}
      {unplaced > 0 && (
        <a class="inv-card" href="#/kho">
          <div class="inv-card-main"><div class="inv-card-code muted">Chưa xếp vị trí</div></div>
          <div class="inv-card-stat"><span class="muted small">{unplaced} thùng</span></div>
          <Icon name="chevronRight" size={18} class="kg-arrow" />
        </a>
      )}
    </div>
  );
}
