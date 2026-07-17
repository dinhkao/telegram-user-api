// Sắp xếp / quản lý thợ (#/tho/sap-xep) — thêm/xoá thợ, tick ⭐ "mặc định" (có trong
// template báo cáo), KÉO-THẢ / ↑↓ sắp thứ tự = thứ tự tự điền cho bảng báo cáo phiếu
// SX mới. Vào từ nút ⚙ ở dashboard #/tho. Dùng chung ReorderList. Data: /api/workers.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { BackLink } from "../nav";
import { listWorkers, addWorker, updateWorker, deleteWorker, reorderWorkers, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { ReorderList } from "../detail/ReorderList";

export function WorkerArrange() {
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [isDef, setIsDef] = useState(true);
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState(0);   // bump → ReorderList seed lại (thêm/xoá thợ)
  const [addOpen, setAddOpen] = useState(false);
  const addInput = useRef<HTMLInputElement>(null);
  useScrollLock(addOpen);
  usePopupBack(addOpen, () => setAddOpen(false));
  useEffect(() => { if (addOpen) requestAnimationFrame(() => addInput.current?.focus()); }, [addOpen]);

  const load = async () => {
    try { setWorkers((await listWorkers()).workers); setErr(""); setSeed((s) => s + 1); }
    catch (e: any) { setErr(e?.message || "Lỗi tải danh sách thợ"); }
  };
  useEffect(() => { load(); }, []);
  // Realtime: thợ đổi từ máy khác (thêm/sửa/xoá/sắp) → tải lại
  useEffect(() => onRealtime((e) => {
    if (e.type === "workers_changed" || e.type === "resync") load();
  }), []);

  const add = async () => {
    const nm = name.trim();
    if (!nm) return;
    setBusy(true);
    try { await addWorker(nm, isDef); setName(""); setAddOpen(false); await load(); toast("Đã thêm thợ", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi thêm thợ", "err"); }
    finally { setBusy(false); }
  };

  // Kéo/↑↓ → lưu bền sort_order (optimistic, KHÔNG bump seed để khỏi reseed nhấp nháy)
  const reorder = (idsMixed: (number | string)[]) => {
    const ids = idsMixed.map(Number);
    setWorkers((ws) => (ws ? ids.map((id) => ws.find((w) => w.id === id)).filter(Boolean) as Worker[] : ws));
    reorderWorkers(ids).catch(() => { toast("Lỗi lưu thứ tự", "err"); load(); });
  };
  // Tick ⭐ → is_default (optimistic)
  const toggleDef = (id: number | string, next: boolean) => {
    setWorkers((ws) => ws?.map((w) => (w.id === id ? { ...w, is_default: next } : w)) || null);
    updateWorker(Number(id), { is_default: next }).catch(() => { toast("Lỗi cập nhật", "err"); load(); });
  };
  const remove = async (id: number | string, nm: string) => {
    if (!(await confirmDialog(`Xoá thợ "${nm}" khỏi danh sách?`, { danger: true }))) return;
    setWorkers((ws) => ws?.filter((x) => x.id !== id) || null); setSeed((s) => s + 1);
    deleteWorker(Number(id)).catch(() => { toast("Lỗi xoá", "err"); load(); });
  };

  if (err && !workers) return <ErrorState msg={err} onRetry={load} />;
  if (!workers) return <Loading />;

  const defCount = workers.filter((w) => w.is_default).length;
  const items = workers.map((w) => ({ id: w.id, name: w.name, on: w.is_default }));

  return (
    <div class="detail">
      <header class="od-appbar">
        <BackLink fallback="#/tho" className="od-back" />
        <div class="od-appttl">Sắp xếp thợ</div>
        <button class="btn primary od-appadd" onClick={() => setAddOpen(true)}><Icon name="plus" size={16} /> Thêm thợ</button>
      </header>

      <div class="card">
        <div class="row space">
          <b>Thợ ({workers.length})</b>
          <span class="muted small"><Icon name="star" size={13} /> mặc định: {defCount}</span>
        </div>
        <div class="muted small wo-hint">Tick <Icon name="star" size={13} /> = có trong mẫu · kéo <Icon name="menu" size={13} /> để sắp thứ tự tự điền</div>
        {workers.length === 0 ? (
          <p class="muted small">Chưa có thợ nào. Thêm ở trên.</p>
        ) : (
          <ReorderList
            items={items}
            seedSig={seed}
            checkKind="star"
            onReorder={reorder}
            onToggle={toggleDef}
            trailing={(it) => (
              <>
                <a class="wo-open" href={`#/sx-tho/${encodeURIComponent(it.name)}`} title="Xem chi tiết">›</a>
                <button class="btn small wo-del" title="Xoá thợ" onClick={() => remove(it.id, it.name)}><Icon name="trash" size={15} /></button>
              </>
            )}
          />
        )}
        <p class="muted small"><Icon name="star" size={13} /> = có trong mẫu báo cáo mặc định, theo đúng thứ tự này.</p>
      </div>

      {addOpen && createPortal(
        <div class="sp-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) setAddOpen(false); }}>
          <div class="sp-sheet">
            <div class="sp-title"><Icon name="plus" size={16} /> Thêm thợ</div>
            <div class="sp-form-pad">
              <input ref={addInput} class="cust-in" type="text" value={name} placeholder="Tên thợ"
                onInput={(e: any) => setName(e.target.value)}
                onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
              <label class="wl-defcheck mt-2">
                <input type="checkbox" checked={isDef} onChange={(e: any) => setIsDef(e.target.checked)} />
                Thêm vào mẫu mặc định (tự điền khi báo cáo trống)
              </label>
            </div>
            <div class="wo-foot">
              <button class="btn" onClick={() => setAddOpen(false)}>Đóng</button>
              <button class="btn primary" disabled={busy || !name.trim()} onClick={add}><Icon name="plus" size={16} /> Thêm</button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
