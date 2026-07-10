// Chi tiết 1 VIỆC (#/viec/:id) — sửa (tiêu đề nếu việc tự do, ghi chú, giao cho,
// hạn), nút Xong to, chip đơn link, TRAO ĐỔI (Comments) + ẢNH (Images/camera)
// qua media scope task (/api/media/task/{id}). Xoá: chỉ việc tự do.
// Data: /api/tasks/{id}. Realtime: tasks_changed → reload.
import { useEffect, useState } from "preact/hooks";
import {
  currentUser, deleteTask, getTask, taskAssignees, updateTask, type Task,
} from "../api";
import { BackLink } from "../nav";
import { Comments } from "../detail/Comments";
import { Images } from "../detail/Images";
import { History } from "../detail/History";
import { onRealtime } from "../realtime";
import { SelectPopup } from "../ui/SelectPopup";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading } from "../ui/states";

const KIND_LABEL: Record<string, string> = {
  free: "Việc tự do", order_step: "Bước của đơn", order_custom: "Việc trong đơn",
};

export function TaskDetail({ id }: { id: number }) {
  const [t, setT] = useState<Task | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");

  const load = () => getTask(id).then(setT).catch((e) => setErr(e?.message || "Không tải được"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    taskAssignees().then((us) => setNames(Object.fromEntries(us.map((u) => [u.username, u.display_name])))).catch(() => {});
  }, []);
  useEffect(() => {
    let tm: any;
    const off = onRealtime((e) => {
      if (e.type === "tasks_changed") { clearTimeout(tm); tm = setTimeout(load, 400); }
    });
    return () => { off(); clearTimeout(tm); };
  }, [id]);

  if (err) return <div class="prod-detail"><BackLink fallback="#/viec" /><p class="error">{err}</p></div>;
  if (!t) return <div class="prod-detail"><BackLink fallback="#/viec" /><Loading /></div>;

  const patch = async (body: any) => {
    try { setT(await updateTask(t.id, body)); } catch (e: any) { toast(e?.message || "Lỗi lưu"); }
  };
  const toggle = () => {
    // Bước mặc định của đơn → hoàn thành ở trang đơn (rule chặn nằm ở đó)
    if (t.kind === "order_step" && t.thread_id) {
      toast("Hoàn thành bước này ở trang đơn", "info");
      window.location.hash = `#/order/${t.thread_id}?focus=od-tasks`;
      return;
    }
    patch({ done: !t.done });
  };
  const remove = async () => {
    if (!(await confirmDialog("Xoá việc này?", { danger: true }))) return;
    try { await deleteTask(t.id); window.location.hash = "#/viec"; } catch (e: any) { toast(e?.message || "Lỗi"); }
  };
  const isAdmin = currentUser()?.role === "admin";

  return (
    <div class="prod-detail tasks-page">
      <div class="prod-detail-head">
        <BackLink fallback="#/viec" />
        <div class="tk-d-head">
          <div class="prod-sp"><Icon name="check" size={18} /> {t.title}</div>
          <div class="muted small">{KIND_LABEL[t.kind]}{t.done && t.done_by ? ` · ✓ ${names[t.done_by] || t.done_by}` : ""}</div>
        </div>
      </div>

      <div class="card">
        <button class={"btn block " + (t.done ? "" : "primary")} onClick={toggle}>
          {t.done ? "↩︎ Mở lại việc" : "✓ Đánh dấu xong"}
        </button>
        {t.kind !== "free" && t.thread_id ? (
          <a class="tk-chip tk-order tk-d-order" href={`#/order/${t.thread_id}`}>
            <Icon name="clipboard" size={13} />
            <span class="tk-otxt">Đơn: {t.order_text || t.order_label || `#${t.thread_id}`}</span>
          </a>
        ) : null}
      </div>

      <div class="card tk-form">
        {t.kind === "free" && (
          <div class="tk-form-row">
            <label class="muted small">Tiêu đề</label>
            <input class="input" value={t.title}
              onChange={(e: any) => { const v = e.target.value.trim(); if (v && v !== t.title) patch({ title: v }); }} />
          </div>
        )}
        <div class="tk-form-row">
          <label class="muted small">Ghi chú</label>
          <textarea class="input" rows={2} value={t.note}
            onChange={(e: any) => { if (e.target.value !== t.note) patch({ note: e.target.value }); }} />
        </div>
        <div class="tk-form-row">
          <label class="muted small">Giao cho</label>
          <SelectPopup value={t.assignee} onChange={(v: string) => patch({ assignee: v })} title="Giao việc cho"
            options={[{ value: "", label: "— Không phân công —" },
              ...Object.entries(names).map(([u, n]) => ({ value: u, label: n }))]} />
        </div>
        <div class="tk-form-row">
          <label class="muted small">Hạn</label>
          <input class="input" type="date" value={t.due_at || ""}
            onChange={(e: any) => patch({ due_at: e.target.value })} />
        </div>
      </div>

      {/* Trao đổi + ảnh — media dùng chung scope 'task' */}
      <Images base={`/api/media/task/${t.id}`} />
      <Comments base={`/api/media/task/${t.id}`} />
      <History base={`/api/media/task/${t.id}`} />

      {t.kind === "free" && isAdmin && (
        <button class="btn danger block" onClick={remove}><Icon name="trash" size={15} /> Xoá việc</button>
      )}
    </div>
  );
}
