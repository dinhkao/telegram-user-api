// Quản lý danh sách thợ (#/tho) — thêm/sửa/xoá thợ, tick "mặc định" (có trong
// template báo cáo). Data: /api/workers. Dùng ở trang sửa báo cáo phiếu SX (picker
// tên + tự điền thợ mặc định).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { listWorkers, addWorker, updateWorker, deleteWorker, type Worker } from "../api";
import { Loading, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";
import { Icon } from "../ui/Icon";

export function WorkerList() {
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [isDef, setIsDef] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setWorkers((await listWorkers()).workers); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải danh sách thợ"); }
  };
  useEffect(() => { load(); }, []);

  const add = async () => {
    const nm = name.trim();
    if (!nm) return;
    setBusy(true);
    try {
      await addWorker(nm, isDef);
      setName("");
      await load();
    } catch (e: any) { toast(e?.message || "Lỗi thêm thợ", "err"); }
    finally { setBusy(false); }
  };

  const toggleDef = async (w: Worker) => {
    setWorkers((ws) => ws?.map((x) => (x.id === w.id ? { ...x, is_default: !x.is_default } : x)) || null);
    try { await updateWorker(w.id, { is_default: !w.is_default }); }
    catch (e: any) { toast(e?.message || "Lỗi cập nhật", "err"); load(); }
  };

  const remove = async (w: Worker) => {
    if (!(await confirmDialog(`Xoá thợ "${w.name}" khỏi danh sách?`, { danger: true }))) return;
    setWorkers((ws) => ws?.filter((x) => x.id !== w.id) || null);
    try { await deleteWorker(w.id); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); load(); }
  };

  if (err && !workers) return <ErrorState msg={err} onRetry={load} />;
  if (!workers) return <Loading />;

  const defCount = workers.filter((w) => w.is_default).length;

  return (
    <div class="detail">
      <header class="od-appbar">
        <BackLink fallback="#/san_xuat" className="od-back" />
        <div class="od-appttl">Danh sách thợ</div>
      </header>

      <div class="card">
        <div class="row space">
          <b>Thêm thợ</b>
        </div>
        <div class="row">
          <input
            type="text"
            value={name}
            placeholder="Tên thợ"
            onInput={(e: any) => setName(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") add(); }}
            style="flex:1"
          />
          <button class="btn primary" disabled={busy || !name.trim()} onClick={add}><Icon name="plus" size={16} /> Thêm</button>
        </div>
        <label class="wl-defcheck">
          <input type="checkbox" checked={isDef} onChange={(e: any) => setIsDef(e.target.checked)} />
          Thêm vào mẫu mặc định (tự điền khi báo cáo trống)
        </label>
      </div>

      <div class="card">
        <div class="row space">
          <b>Thợ ({workers.length})</b>
          <span class="muted small">⭐ mặc định: {defCount}</span>
        </div>
        {workers.length === 0 ? (
          <p class="muted small">Chưa có thợ nào. Thêm ở trên.</p>
        ) : (
          <ul class="wl-list">
            {workers.map((w) => (
              <li class="wl-row" key={w.id}>
                <button
                  class={"wl-star" + (w.is_default ? " on" : "")}
                  title={w.is_default ? "Bỏ khỏi mẫu mặc định" : "Thêm vào mẫu mặc định"}
                  onClick={() => toggleDef(w)}
                >{w.is_default ? "⭐" : "☆"}</button>
                <a class="wl-name wl-link" href={`#/sx-tho/${encodeURIComponent(w.name)}`}>
                  {w.name} <span class="wl-arrow">›</span>
                </a>
                <button class="btn small" title="Xoá thợ" onClick={() => remove(w)}><Icon name="trash" size={15} /></button>
              </li>
            ))}
          </ul>
        )}
        <p class="muted small">⭐ = có trong mẫu báo cáo mặc định. Sửa báo cáo phiếu SX sẽ tự điền các thợ này.</p>
      </div>
    </div>
  );
}
