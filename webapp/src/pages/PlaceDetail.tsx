// Chi tiết 1 vị trí kho — đổi tên, ghi chú, ảnh + trao đổi + lịch sử (media scope
// 'place'), xoá (admin), lưới thùng đang ở vị trí này.
// Data: listPlaces (tìm theo id) + allBoxes (lọc place_id). Realtime reload.
import { useEffect, useState } from "preact/hooks";

let memView: "grid" | "compact" = "grid";   // nhớ kiểu xem thùng khi rời trang (mặc định Ô THÙNG)
import { listPlaces, allBoxes, renamePlace, setPlaceNote, deletePlace, currentUser, soVN, createStocktake, listPlaceStocktakes, type Place, type KhoBox, type Stocktake } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";
import { CompactBoxList } from "../detail/CompactBoxList";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";

export function PlaceDetail({ id }: { id: string }) {
  const pid = Number(id);
  const [place, setPlace] = useState<Place | null | undefined>(undefined);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [stocktakes, setStocktakes] = useState<Stocktake[]>([]);
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const load = async () => {
    try {
      const [pl, bx, st] = await Promise.all([listPlaces(), allBoxes(), listPlaceStocktakes(pid)]);
      const p = pl.find((x) => x.id === pid) || null;
      setPlace(p); setName(p?.name || "");
      setBoxes(bx.filter((b) => b.place_id === pid));
      setStocktakes(st);
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
  const startStocktake = async () => {
    setBusy(true);
    try {
      const { stocktake, resumed } = await createStocktake(pid);
      if (resumed) toast("Tiếp tục phiếu kiểm kho đang mở", "info");
      window.location.hash = `#/kiem-kho/${stocktake.id}`;
    } catch (e: any) { toast(e?.message || "Không tạo được phiếu kiểm kho", "err"); }
    finally { setBusy(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (place === undefined) return <Loading />;
  if (place === null) return <div class="muted">Không tìm thấy vị trí. <a href="#/vi-tri">← Vị trí kho</a></div>;

  const rem = boxes.reduce((s, b) => s + (b.disabled ? 0 : b.remaining), 0);
  const nStock = boxes.filter((b) => (b.remaining ?? b.quantity ?? 0) > 0).length;   // đếm thùng còn hàng

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
          <div class="prod-date muted">{soVN(rem)} tồn · {nStock} thùng</div>
        </div>
      </div>

      <div class="place-action-grid">
        <button class="btn primary" disabled={busy} onClick={startStocktake}>
          <Icon name="clipboard" size={17} /> {stocktakes[0]?.status === "draft" ? "Tiếp tục kiểm kho" : "Kiểm kho"}
        </button>
        <a class="btn" href={`#/vi-tri/${pid}/timeline`}>
          <Icon name="history" size={16} /> Timeline kho
        </a>
      </div>

      {stocktakes.length > 0 && (
        <section class="card place-stocktakes">
          <label class="card-label"><Icon name="clipboard" size={15} /> Phiếu kiểm kho gần đây</label>
          <div class="place-stocktake-list">
            {stocktakes.slice(0, 5).map((s) => (
              <a href={`#/kiem-kho/${s.id}`} class="place-stocktake-link" key={s.id}>
                <span class={`place-stocktake-dot ${s.status}`} />
                <span>
                  <b>Phiếu #{s.id} {s.status === "draft" && s.stale?.changed && <em class="place-stocktake-stale">⚠ cần cập nhật</em>}</b>
                  <small>{fmtDateTimeVN(s.captured_at)} · {s.summary.counted_count}/{s.summary.box_count} thùng</small>
                </span>
                <strong class={s.status === "completed" && (s.summary.difference_total || 0) !== 0 ? "has-diff" : ""}>
                  {s.status === "voided" ? "Đã huỷ" : s.status === "draft" ? "Đang kiểm" : `Lệch ${(s.summary.difference_total || 0) > 0 ? "+" : ""}${soVN(s.summary.difference_total || 0)}`}
                </strong>
                <Icon name="chevronRight" size={16} />
              </a>
            ))}
          </div>
        </section>
      )}

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
        if (boxes.length === 0) return <EmptyState>Chưa có thùng ở vị trí này. Gán vị trí ở chi tiết thùng.</EmptyState>;
        if (live.length === 0) return <EmptyState>Kho này không còn thùng nào có hàng.</EmptyState>;
        return (
          <>
            <div class="row" style={{ justifyContent: "flex-end", gap: "6px", marginBottom: "6px" }}>
              <button class={"chip" + (view === "grid" ? " active" : "")} onClick={() => setView("grid")}>Ô thùng</button>
              <button class={"chip" + (view === "compact" ? " active" : "")} onClick={() => setView("compact")}>Gọn</button>
            </div>
            {view === "compact" ? (
              <CompactBoxList boxes={live} />
            ) : (
              <div class="kho-groups">
                {groups.map(([pcode, bs]) => (
                  <section class="kho-group" key={pcode}>
                    <a class="kho-group-h" href={`#/kho/${encodeURIComponent(pcode)}`}>
                      <b>{pcode}</b>
                      <span class="muted small">{soVN(sumRem(bs))} tồn · {bs.length} thùng →</span>
                    </a>
                    <BoxLabelGrid boxes={bs} dense />
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
