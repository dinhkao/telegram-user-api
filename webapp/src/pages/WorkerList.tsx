// Danh sách thợ (#/tho) — CHỈ HIỂN THỊ list, bấm 1 thợ → chi tiết thợ (#/sx-tho/:name).
// Nút ⚙ → trang sắp xếp/quản lý (#/tho/sap-xep, WorkerArrange). KHÔNG sắp xếp/edit ở đây.
// Data: /api/workers. Realtime workers_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { listWorkers, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function WorkerList() {
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [err, setErr] = useState("");

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
        {workers.length === 0 ? (
          <p class="muted small">Chưa có thợ nào. Bấm <Icon name="settings" size={13} /> để thêm.</p>
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
