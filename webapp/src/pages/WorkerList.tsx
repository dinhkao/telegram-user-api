// Danh sách thợ (#/tho) — list + nút ➕ TẠO nhân viên mới (promptDialog tên); bấm 1 thợ
// → chi tiết thợ (#/sx-tho/:name). Nút ⚙ → trang sắp xếp/quản lý (#/tho/sap-xep,
// WorkerArrange — sắp thứ tự/⭐/xoá vẫn ở đó). Data: /api/workers. Realtime
// workers_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { addWorker, listWorkers, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { toast, promptDialog } from "../ui/feedback";

export function WorkerList() {
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [err, setErr] = useState("");
  const [adding, setAdding] = useState(false);

  const addNew = async () => {
    if (adding) return;
    const nm = (await promptDialog("Tên nhân viên mới", { placeholder: "vd: Nguyễn Văn A", okLabel: "Tạo" }))?.trim();
    if (!nm) return;
    if (workers?.some((w) => w.name.trim().toLowerCase() === nm.toLowerCase())) {
      toast(`Đã có nhân viên tên "${nm}"`, "err");
      return;
    }
    setAdding(true);
    try {
      await addWorker(nm, false);
      toast(`Đã tạo nhân viên "${nm}"`, "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo nhân viên", "err");
    } finally {
      setAdding(false);
    }
  };

  const load = async () => {
    try { setWorkers((await listWorkers()).workers); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải danh sách thợ"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => { if (e.type === "workers_changed" || e.type === "resync") load(); }), []);

  if (err && !workers) return <ErrorState msg={err} onRetry={load} />;
  if (!workers) return <Loading />;

  const defCount = workers.filter((w) => w.is_default).length;

  return (
    <div class="detail">
      <header class="od-appbar">
        <BackLink fallback="#/san_xuat" className="od-back" />
        <div class="od-appttl">Danh sách thợ</div>
        <a class="icon-btn od-appadd" href="#/tho/sap-xep" title="Sắp xếp / quản lý thợ"><Icon name="settings" size={20} /></a>
      </header>

      <div class="card">
        <div class="row space">
          <b>Thợ ({workers.length})</b>
          <span class="muted small"><Icon name="star" size={13} /> mặc định: {defCount}</span>
        </div>
        <button class="btn wl-add-btn" onClick={addNew} disabled={adding}>
          <Icon name="plus" size={16} /> {adding ? "Đang tạo…" : "Thêm nhân viên"}
        </button>
        {workers.length === 0 ? (
          <EmptyState icon="👷">Chưa có nhân viên nào. Bấm "Thêm nhân viên" để tạo.</EmptyState>
        ) : (
          <div class="wl-list">
            {workers.map((w) => (
              <a class="wl-row" href={`#/sx-tho/${encodeURIComponent(w.name)}`} key={w.id}>
                <span class={"wl-star" + (w.is_default ? " on" : "")}>{w.is_default ? <Icon name="star" size={15} /> : null}</span>
                <span class="wl-name">{w.name}</span>
                <Icon name="chevronRight" size={17} class="wl-chev" />
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
