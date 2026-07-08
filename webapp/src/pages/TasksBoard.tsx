// Dashboard VIỆC (#/viec) — task list toàn cục: việc tự do + việc mirror từ đơn.
// Chips lọc (đang mở/của tôi/tự do/từ đơn/quá hạn/xong), card việc (check xong
// tại chỗ, hạn đỏ khi quá, chip đơn link #/order), tạo việc (sheet: tiêu đề/
// ghi chú/giao cho/hạn/link đơn qua search), LỊCH (ScrollCalendar theo hạn).
// Data: /api/tasks*. Realtime: tasks_changed.
import { useEffect, useState } from "preact/hooks";
import {
  createTask, currentUser, getJSON, listTasks, taskAssignees, taskDay, taskDays,
  updateTask, type Task, type TaskCounts,
} from "../api";
import { ScrollCalendar, type CalDays } from "../detail/ScrollCalendar";
import { onRealtime } from "../realtime";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { SelectPopup } from "../ui/SelectPopup";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { EmptyState, SkeletonList } from "../ui/states";

const FLT: { k: string; t: string; c?: keyof TaskCounts }[] = [
  { k: "open", t: "Đang mở", c: "open" },
  { k: "mine", t: "Của tôi", c: "mine" },
  { k: "free", t: "Việc tự do", c: "free" },
  { k: "order", t: "Từ đơn", c: "order" },
  { k: "overdue", t: "Quá hạn", c: "overdue" },
  { k: "done", t: "Xong", c: "done" },
];

const dmy = (d?: string | null) => (d ? `${d.slice(8)}/${d.slice(5, 7)}` : "");

/** Card 1 việc — dùng chung list + popup lịch. */
export function TaskCard({ t, today, names, onToggle }: {
  t: Task; today: string; names: Record<string, string>;
  onToggle: (t: Task) => void;
}) {
  const overdue = !t.done && t.due_at && t.due_at < today;
  return (
    <li class={"task-card" + (t.done ? " tk-done" : "")}>
      <button class={"tk-check" + (t.done ? " on" : "")} onClick={() => onToggle(t)} aria-label="Xong">
        {t.done ? <Icon name="check" size={15} /> : null}
      </button>
      <a class="tk-main" href={`#/viec/${t.id}`}>
        <span class="tk-title">{t.title}</span>
        <span class="tk-meta">
          {t.kind !== "free" && t.thread_id ? (
            <span class="tk-chip tk-order" onClick={(e: any) => { e.preventDefault(); e.stopPropagation(); window.location.hash = `#/order/${t.thread_id}`; }}>
              <Icon name="clipboard" size={11} /> {t.order_label && t.order_label !== "?" ? t.order_label : `#${t.thread_id}`}
            </span>
          ) : null}
          {t.assignee ? <span class="tk-chip"><Icon name="user" size={11} /> {names[t.assignee] || t.assignee}</span> : null}
          {t.due_at ? <span class={"tk-chip tk-due" + (overdue ? " od" : "")}><Icon name="calendar" size={11} /> {dmy(t.due_at)}</span> : null}
          {t.done && t.done_by ? <span class="tk-chip tk-by">✓ {names[t.done_by] || t.done_by}</span> : null}
        </span>
      </a>
    </li>
  );
}

export function TasksBoard() {
  const [mode, setMode] = useState<"list" | "cal">("list");
  const [flt, setFlt] = useState("open");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [counts, setCounts] = useState<TaskCounts | null>(null);
  const [today, setToday] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [names, setNames] = useState<Record<string, string>>({});

  const load = async (f = flt, p = 1) => {
    setLoading(true);
    try {
      const d = await listTasks(f, p);
      setTasks(p === 1 ? d.tasks : (prev => [...prev, ...d.tasks])(tasks));
      setCounts(d.counts); setToday(d.today); setTotalPages(d.total_pages); setPage(p);
    } catch (e: any) { toast(e?.message || "Lỗi tải việc"); }
    setLoading(false);
  };
  useEffect(() => { load("open", 1); }, []);
  useEffect(() => {
    taskAssignees().then((us) => setNames(Object.fromEntries(us.map((u) => [u.username, u.display_name])))).catch(() => {});
  }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "tasks_changed") { clearTimeout(t); t = setTimeout(() => load(flt, 1), 400); }
    });
    return () => { off(); clearTimeout(t); };
  }, [flt]);

  const toggle = async (t: Task) => {
    try {
      const nt = await updateTask(t.id, { done: !t.done });
      setTasks((prev) => prev.map((x) => (x.id === t.id ? nt : x)));
      load(flt, 1);
    } catch (e: any) { toast(e?.message || "Lỗi"); }
  };

  // ── lịch theo hạn ──
  const [calDays, setCalDays] = useState<CalDays>(new Map());
  useEffect(() => {
    if (mode !== "cal") return;
    taskDays().then((list) => setCalDays(new Map(list.map((x) => [x.d, { o: x.o, p: x.p }])))).catch(() => {});
  }, [mode]);
  const [pick, setPick] = useState<string | null>(null);
  const [dayItems, setDayItems] = useState<Task[] | null>(null);
  const openDay = (d: string) => { setPick(d); setDayItems(null); taskDay(d).then(setDayItems).catch(() => setDayItems([])); };
  const closeDay = () => { setPick(null); setDayItems(null); };
  useScrollLock(!!pick);
  usePopupBack(!!pick, closeDay);

  // ── tạo việc ──
  const [creating, setCreating] = useState(false);

  return (
    <div class="tasks-page">
      <div class="row space tk-head">
        <b class="page-title"><Icon name="check" size={18} /> Việc</b>
        <span class="img-head-act">
          <div class="view-slider" role="group">
            <button class={mode === "list" ? "vs-seg on" : "vs-seg"} onClick={() => setMode("list")} title="Danh sách"><Icon name="menu" size={15} /></button>
            <button class={mode === "cal" ? "vs-seg on" : "vs-seg"} onClick={() => setMode("cal")} title="Lịch"><Icon name="calendar" size={15} /></button>
          </div>
          <button class="btn small primary" onClick={() => setCreating(true)}><Icon name="plus" size={15} /> Thêm việc</button>
        </span>
      </div>

      {mode === "list" && (
        <>
          <div class="chips">
            {FLT.map((f) => (
              <button key={f.k} class={"chip" + (flt === f.k ? " active" : "") + (f.k === "overdue" && counts?.overdue ? " chip-danger" : "")}
                onClick={() => { setFlt(f.k); load(f.k, 1); }}>
                {f.t}{counts && f.c != null ? ` (${counts[f.c]})` : ""}
              </button>
            ))}
          </div>
          {loading && !tasks.length ? <SkeletonList rows={5} /> : null}
          {!loading && !tasks.length ? <EmptyState>Không có việc nào</EmptyState> : null}
          <ul class="task-list">
            {tasks.map((t) => <TaskCard key={t.id} t={t} today={today} names={names} onToggle={toggle} />)}
          </ul>
          {page < totalPages && (
            <button class="btn block" onClick={() => load(flt, page + 1)} disabled={loading}>Tải thêm</button>
          )}
        </>
      )}

      {mode === "cal" && (
        <ScrollCalendar days={calDays} legend={{ o: "chưa xong", p: "đã xong" }} onPick={openDay} />
      )}

      {pick && (
        <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) closeDay(); }}>
          <div class="modal-sheet cc-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="calendar" size={16} /> Hạn {pick ? `${pick.slice(8)}/${pick.slice(5, 7)}/${pick.slice(0, 4)}` : ""}
              <button class="link-btn cc-x" onClick={closeDay}><Icon name="close" size={18} /></button>
            </div>
            {dayItems == null ? <p class="muted small">Đang tải…</p>
              : dayItems.length ? (
                <ul class="task-list cc-list">
                  {dayItems.map((t) => <TaskCard key={t.id} t={t} today={today} names={names} onToggle={toggle} />)}
                </ul>
              ) : <EmptyState>Không có việc hạn ngày này</EmptyState>}
          </div>
        </div>
      )}

      {creating && <CreateTaskSheet names={names} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(flt, 1); }} />}
    </div>
  );
}

/** Sheet tạo việc: tiêu đề, ghi chú, giao cho (SelectPopup), hạn, link đơn (search). */
function CreateTaskSheet({ names, onClose, onCreated }: {
  names: Record<string, string>; onClose: () => void; onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState(currentUser()?.username || "");
  const [due, setDue] = useState("");
  const [orderQ, setOrderQ] = useState("");
  const [orderHits, setOrderHits] = useState<any[]>([]);
  const [linked, setLinked] = useState<{ thread_id: number; label: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  // search đơn để link (tái dùng /api/orders?search=)
  useEffect(() => {
    if (!orderQ.trim()) { setOrderHits([]); return; }
    const t = setTimeout(async () => {
      try {
        const d = await getJSON(`/api/orders?search=${encodeURIComponent(orderQ.trim())}&page=1`, { cache: false });
        setOrderHits((d.orders || []).slice(0, 6));
      } catch { setOrderHits([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [orderQ]);

  const save = async () => {
    if (!title.trim()) { toast("Nhập tiêu đề việc"); return; }
    setBusy(true);
    try {
      await createTask({
        title: title.trim(), note: note.trim(), assignee, due_at: due || undefined,
        thread_id: linked?.thread_id,
      });
      toast("Đã tạo việc");
      onCreated();
    } catch (e: any) { toast(e?.message || "Lỗi tạo việc"); }
    setBusy(false);
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet cc-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="plus" size={16} /> Thêm việc
          <button class="link-btn cc-x" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>
        <div class="tk-form cc-list">
          <input class="input" placeholder="Việc gì?" value={title} onInput={(e: any) => setTitle(e.target.value)} />
          <textarea class="input" rows={2} placeholder="Ghi chú (tuỳ chọn)" value={note} onInput={(e: any) => setNote(e.target.value)} />
          <div class="tk-form-row">
            <label class="muted small">Giao cho</label>
            <SelectPopup value={assignee} onChange={setAssignee} title="Giao việc cho"
              options={[{ value: "", label: "— Không phân công —" },
                ...Object.entries(names).map(([u, n]) => ({ value: u, label: n }))]} />
          </div>
          <div class="tk-form-row">
            <label class="muted small">Hạn</label>
            <input class="input" type="date" value={due} onInput={(e: any) => setDue(e.target.value)} />
          </div>
          <div class="tk-form-row">
            <label class="muted small">Link đơn</label>
            {linked ? (
              <span class="tk-chip tk-order">{linked.label} <button class="link-btn" onClick={() => setLinked(null)}>✕</button></span>
            ) : (
              <input class="input" placeholder="Tìm đơn (khách, nội dung…)" value={orderQ} onInput={(e: any) => setOrderQ(e.target.value)} />
            )}
          </div>
          {!linked && orderHits.length > 0 && (
            <div class="tk-hits">
              {orderHits.map((o) => (
                <button key={o.thread_id} class="tk-hit" onClick={() => { setLinked({ thread_id: o.thread_id, label: o.customer || o.topic_name || `#${o.thread_id}` }); setOrderQ(""); }}>
                  <b>{o.customer || o.topic_name || `#${o.thread_id}`}</b>
                  <span class="muted small"> {(o.text || "").slice(0, 40)}</span>
                </button>
              ))}
            </div>
          )}
          <button class="btn primary block" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : "Tạo việc"}</button>
        </div>
      </div>
    </div>
  );
}
