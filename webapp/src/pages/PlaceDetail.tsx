// Chi tiết 1 vị trí kho — đổi tên, xoá (admin), lưới thùng đang ở vị trí này.
// Data: listPlaces (tìm theo id) + allBoxes (lọc place_id). Realtime reload.
import { useEffect, useState } from "preact/hooks";
import { listPlaces, allBoxes, renamePlace, deletePlace, currentUser, soVN, type Place, type KhoBox } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";

export function PlaceDetail({ id }: { id: string }) {
  const pid = Number(id);
  const [place, setPlace] = useState<Place | null | undefined>(undefined);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const load = async () => {
    try {
      const [pl, bx] = await Promise.all([listPlaces(), allBoxes()]);
      const p = pl.find((x) => x.id === pid) || null;
      setPlace(p); setName(p?.name || "");
      setBoxes(bx.filter((b) => b.place_id === pid));
    } catch (e: any) { setErr(e?.message || "Lỗi tải vị trí"); }
  };
  useEffect(() => { load(); }, [pid]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed") load();
  }), [pid]);

  const saveName = async () => {
    const n = name.trim();
    if (!n || n === place?.name) { setEditing(false); return; }
    setBusy(true);
    try { const p = await renamePlace(pid, n); setPlace(p); setEditing(false); toast("✅ Đã đổi tên", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi đổi tên", "err"); }
    finally { setBusy(false); }
  };
  const doDelete = async () => {
    if (!(await confirmDialog(`Xoá vị trí "${place?.name}"? Thùng đang ở đây sẽ về "chưa xếp".`, { danger: true, okLabel: "Xoá" }))) return;
    setBusy(true);
    try { await deletePlace(pid); window.location.hash = "#/vi-tri"; }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); setBusy(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (place === undefined) return <Loading />;
  if (place === null) return <div class="muted">Không tìm thấy vị trí. <a href="#/vi-tri">← Vị trí kho</a></div>;

  const rem = boxes.reduce((s, b) => s + (b.disabled ? 0 : b.remaining), 0);

  return (
    <div class="inv-dash">
      <div class="prod-detail-head">
        <BackLink fallback="#/vi-tri" />
        <div style={{ flex: 1 }}>
          {editing ? (
            <span class="row" style={{ gap: "6px" }}>
              <input class="inv-search" autofocus value={name} onInput={(e: any) => setName(e.target.value)}
                onKeyDown={(e: any) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") setEditing(false); }} />
              <button class="btn small primary" disabled={busy} onClick={saveName}>Lưu</button>
              <button class="btn small" onClick={() => { setEditing(false); setName(place.name); }}>✕</button>
            </span>
          ) : (
            <div class="prod-sp big" onClick={() => setEditing(true)} style={{ cursor: "pointer" }}>
              <Icon name="box" size={18} /> {place.name} <Icon name="edit" size={15} class="kg-arrow" />
            </div>
          )}
          <div class="prod-date muted">{soVN(rem)} tồn · {boxes.length} thùng</div>
        </div>
      </div>

      {boxes.length === 0 ? (
        <EmptyState>Chưa có thùng ở vị trí này. Gán vị trí ở chi tiết thùng.</EmptyState>
      ) : (
        <BoxLabelGrid boxes={boxes} />
      )}

      {isAdmin && (
        <section class="card" style={{ marginTop: "14px" }}>
          <button class="btn danger block" disabled={busy} onClick={doDelete}>
            <Icon name="trash" size={16} /> Xoá vị trí (admin)
          </button>
        </section>
      )}
    </div>
  );
}
