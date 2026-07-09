// Chi tiết 1 vị trí kho — đổi tên, ghi chú, ảnh + trao đổi + lịch sử (media scope
// 'place'), xoá (admin), lưới thùng đang ở vị trí này.
// Data: listPlaces (tìm theo id) + allBoxes (lọc place_id). Realtime reload.
import { useEffect, useState } from "preact/hooks";

let memView: "grid" | "compact" = "grid";   // nhớ kiểu xem thùng khi rời trang
import { listPlaces, allBoxes, renamePlace, setPlaceNote, deletePlace, currentUser, soVN, type Place, type KhoBox } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";

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
  // Ghi chú vị trí — sửa tại chỗ, lưu khi bấm
  const [noteEdit, setNoteEdit] = useState<string | null>(null); // null = đang xem
  const [view, setView] = useState<"grid" | "compact">(memView);
  useEffect(() => { memView = view; }, [view]);
  const saveNote = async () => {
    if (noteEdit === null) return;
    setBusy(true);
    try { const p = await setPlaceNote(pid, noteEdit.trim()); setPlace(p); setNoteEdit(null); toast("✅ Đã lưu ghi chú", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu ghi chú", "err"); }
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

      <a class="btn block pt-open-btn" href={`#/vi-tri/${pid}/timeline`}>
        <Icon name="history" size={16} /> Timeline biến động kho →
      </a>

      <section class="card">
        <label class="card-label"><Icon name="edit" size={15} /> Ghi chú</label>
        {noteEdit === null ? (
          <div onClick={() => setNoteEdit(place.note || "")} style={{ cursor: "pointer" }}>
            {place.note
              ? <p style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{place.note}</p>
              : <p class="muted small" style={{ margin: "4px 0" }}>Chưa có ghi chú — bấm để thêm.</p>}
          </div>
        ) : (
          <>
            <textarea class="inv-search" rows={3} style={{ width: "100%", resize: "vertical" }} autofocus
              value={noteEdit} onInput={(e: any) => setNoteEdit(e.target.value)} />
            <div class="row" style={{ gap: "6px", marginTop: "6px" }}>
              <button class="btn small primary" disabled={busy} onClick={saveNote}>Lưu</button>
              <button class="btn small" onClick={() => setNoteEdit(null)}>✕ Huỷ</button>
            </div>
          </>
        )}
      </section>

      {(() => {
        // Chi tiết kho: CHỈ hiện thùng còn hàng (thùng đã hết xem ở chi tiết SP), GOM THEO SP
        const live = boxes.filter((b) => (b.remaining ?? b.quantity ?? 0) > 0);
        const remOf = (b: any) => Math.max(0, b.remaining ?? b.quantity ?? 0);
        const g = new Map<string, typeof live>();
        for (const b of live) { const a = g.get(b.product_code); if (a) a.push(b); else g.set(b.product_code, [b]); }
        const sumRem = (bs: typeof live) => bs.reduce((s, b) => s + remOf(b), 0);
        const groups = [...g.entries()].sort((a, b) => sumRem(b[1]) - sumRem(a[1]) || a[0].localeCompare(b[0]));
        const num = (b: any) => (b.box_code || "").split("-").pop() || b.box_code;
        if (boxes.length === 0) return <EmptyState>Chưa có thùng ở vị trí này. Gán vị trí ở chi tiết thùng.</EmptyState>;
        if (live.length === 0) return <EmptyState>Kho này không còn thùng nào có hàng.</EmptyState>;
        return (
          <>
            <div class="row" style={{ justifyContent: "flex-end", gap: "6px", marginBottom: "6px" }}>
              <button class={"chip" + (view === "grid" ? " active" : "")} onClick={() => setView("grid")}>Ô thùng</button>
              <button class={"chip" + (view === "compact" ? " active" : "")} onClick={() => setView("compact")}>Gọn</button>
            </div>
            {view === "compact" ? (
              <div class="pd-compact">
                {groups.map(([pcode, bs]) => (
                  <div class="pd-crow" key={pcode}>
                    <a class="pd-csp" href={`#/kho/${encodeURIComponent(pcode)}`}>{pcode}</a>
                    <span class="pd-cboxes">
                      {bs.slice().sort((a, b) => num(a).localeCompare(num(b))).map((b) => (
                        <a class="pd-cbox" key={b.id} href={`#/thung/${b.id}`}
                          title={`Thùng ${num(b)} · còn ${soVN(remOf(b))} ${(b as any).product_unit || "cây"}`}>
                          <span class="pd-cbn">{num(b)}</span><span class="pd-cq">{soVN(remOf(b))}</span>
                        </a>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div class="kho-groups">
                {groups.map(([pcode, bs]) => (
                  <section class="kho-group" key={pcode}>
                    <a class="kho-group-h" href={`#/kho/${encodeURIComponent(pcode)}`}>
                      <b>{pcode}</b>
                      <span class="muted small">{soVN(sumRem(bs))} tồn · {bs.length} thùng →</span>
                    </a>
                    <BoxLabelGrid boxes={bs} />
                  </section>
                ))}
              </div>
            )}
          </>
        );
      })()}

      <Images base={`/api/media/place/${pid}`} />
      <Comments base={`/api/media/place/${pid}`} />
      <History base={`/api/media/place/${pid}`} />

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
