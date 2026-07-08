// Dashboard VIỆC (#/viec) — task list toàn cục: việc tự do + việc mirror từ đơn.
// KPI 4 ô (đang mở/của tôi/quá hạn/xong — chạm = lọc), chips loại việc (tự do/
// thêm/từ đơn) kèm số, list chia mục theo ngày (Hôm nay/Hôm qua/…), card việc
// (check xong tại chỗ, hạn đỏ khi quá, chip đơn link #/order), tạo việc (sheet),
// LỊCH (ScrollCalendar theo hạn). Data: /api/tasks*. Realtime: tasks_changed.
import { useEffect, useRef, useState } from "preact/hooks";
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
import { SearchBar, FilterActiveBar } from "../ui/SearchBar";
import { toast } from "../ui/feedback";
import { EmptyState, SkeletonList } from "../ui/states";
import { fmtRelative } from "../format";

// 4 KPI tile (trạng thái) + chips loại việc — cùng 1 không gian filter `flt`
const STAT: { k: string; t: string; c: keyof TaskCounts; icon: string; cls: string }[] = [
  { k: "open", t: "Đang mở", c: "open", icon: "clock", cls: "st-blue" },
  { k: "mine", t: "Của tôi", c: "mine", icon: "user", cls: "st-warn" },
  { k: "overdue", t: "Quá hạn", c: "overdue", icon: "bell", cls: "st-red" },
  { k: "done", t: "Xong", c: "done", icon: "check", cls: "st-ok" },
];
const KIND: { k: string; t: string; c: keyof TaskCounts }[] = [
  { k: "free", t: "Việc tự do", c: "free" },
  { k: "extra", t: "Việc thêm", c: "extra" },   // KHÔNG phải 5 bước mặc định của đơn
  { k: "order", t: "Từ đơn", c: "order" },
];
const FLT = [...STAT, ...KIND];

const dmy = (d?: string | null) => (d ? `${d.slice(8)}/${d.slice(5, 7)}` : "");

// màu avatar theo tên (ổn định) — nhận diện người nhanh trong list dài
const AVA_COLORS = ["#1a73e8", "#188038", "#b26b00", "#7b3ff2", "#c2185b", "#00838f"];
const avaColor = (s: string) =>
  AVA_COLORS[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % AVA_COLORS.length];

/** Card 1 việc — dùng chung list + popup lịch. Accent trái theo trạng thái
 *  (đỏ quá hạn / xanh dương đang mở / xanh lá xong), checkbox tròn, note 1 dòng. */
export function TaskCard({ t, today, names, onToggle }: {
  t: Task; today: string; names: Record<string, string>;
  onToggle: (t: Task) => void;
}) {
  const overdue = !t.done && t.due_at && t.due_at < today;
  const state = t.done ? "done" : overdue ? "od" : "open";
  const who = t.assignee ? (names[t.assignee] || t.assignee) : "";
  return (
    <li class={`task-card tks-${state}`}>
      <button class={"tk-check" + (t.done ? " on" : "")} onClick={() => onToggle(t)} aria-label="Xong">
        {t.done ? <Icon name="check" size={14} /> : null}
      </button>
      <a class="tk-main" href={`#/viec/${t.id}`}>
        <span class="tk-row1">
          <span class="tk-title">{t.title}</span>
          <span class="tk-time">{fmtRelative(new Date(t.created_at * 1000).toISOString())}</span>
        </span>
        {t.note ? <span class="tk-note">{t.note}</span> : null}
        <span class="tk-meta">
          {t.kind !== "free" && t.thread_id ? (
            <span class="tk-chip tk-order" onClick={(e: any) => { e.preventDefault(); e.stopPropagation(); window.location.hash = `#/order/${t.thread_id}`; }}>
              <Icon name="clipboard" size={11} /> {t.order_label && t.order_label !== "?" ? t.order_label : `#${t.thread_id}`}
            </span>
          ) : null}
          {t.due_at ? <span class={"tk-chip tk-due" + (overdue ? " od" : "")}><Icon name="calendar" size={11} /> {overdue ? "Quá hạn " : ""}{dmy(t.due_at)}</span> : null}
          {who ? (
            <span class="tk-chip tk-who"><span class="tk-ava" style={{ background: avaColor(who) }}>{who[0]}</span> {who}</span>
          ) : null}
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
  const [q, setQ] = useState("");
  const fltRef = useRef("open");   // closure-safe cho debounce search
  const changeFlt = (f: string) => { fltRef.current = f; setFlt(f); };
  // lọc theo NGƯỜI LÀM (avatar row) — ref để lazy-load/realtime/debounce khỏi dính closure cũ
  const [who, setWho] = useState("");
  const whoRef = useRef("");
  const changeWho = (w: string) => { whoRef.current = w; setWho(w); };

  const load = async (f = fltRef.current, p = 1, qq = q, w = whoRef.current) => {
    setLoading(true);
    try {
      const d = await listTasks(f, p, qq.trim(), w);
      setTasks(p === 1 ? d.tasks : (prev => [...prev, ...d.tasks])(tasks));
      setCounts(d.counts); setToday(d.today); setTotalPages(d.total_pages); setPage(p);
    } catch (e: any) { toast(e?.message || "Lỗi tải việc"); }
    setLoading(false);
  };
  useEffect(() => {
    // deep-link #/viec?filter=… (badge app bar → Của tôi)
    const fm = window.location.hash.match(/[?&]filter=([a-z_]+)/);
    const f = fm && FLT.some((x) => x.k === fm[1]) ? fm[1] : "open";
    if (fm) history.replaceState(null, "", "#/viec");
    changeFlt(f);
    load(f, 1);
  }, []);
  // search: gõ → debounce 300ms tải lại (bỏ lần mount đầu — khỏi đè deep-link;
  // đọc filter qua ref để không dính closure cũ)
  const qFirst = useRef(true);
  useEffect(() => {
    if (qFirst.current) { qFirst.current = false; return; }
    const t = setTimeout(() => load(fltRef.current, 1, q), 300);
    return () => clearTimeout(t);
  }, [q]);
  // người làm: tên + SỐ VIỆC CHƯA XONG (vòng avatar đỏ/xanh theo còn việc hay không)
  const [openBy, setOpenBy] = useState<Record<string, number>>({});
  const loadPeople = () => taskAssignees().then((us) => {
    setNames(Object.fromEntries(us.map((u) => [u.username, u.display_name])));
    setOpenBy(Object.fromEntries(us.map((u) => [u.username, u.open || 0])));
  }).catch(() => {});
  useEffect(() => { loadPeople(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "tasks_changed") {
        clearTimeout(t);
        t = setTimeout(() => { load(fltRef.current, 1); loadPeople(); }, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [flt]);

  const toggle = async (t: Task) => {
    try {
      const nt = await updateTask(t.id, { done: !t.done });
      setTasks((prev) => prev.map((x) => (x.id === t.id ? nt : x)));
      load(flt, 1); loadPeople();
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

  // ── LAZY LOAD: chạm đáy danh sách → tự tải trang kế ──
  const moreRef = useRef<HTMLDivElement>(null);
  const pgRef = useRef({ page: 1, totalPages: 1, loading: false, q: "" });
  pgRef.current = { page, totalPages, loading, q };
  useEffect(() => {
    const el = moreRef.current;
    if (!el) return;
    const io = new IntersectionObserver((ents) => {
      const st = pgRef.current;
      if (ents.some((x) => x.isIntersecting) && !st.loading && st.page < st.totalPages)
        load(fltRef.current, st.page + 1, st.q);
    }, { rootMargin: "300px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [tasks.length, mode]);

  // ── tạo việc ──
  const [creating, setCreating] = useState(false);

  // chạm avatar = lọc việc CHƯA XONG của người đó (chạm lại = bỏ);
  // avatar CỦA MÌNH = chính filter "Của tôi" (1 trạng thái, sáng cả 2 nơi)
  const me = currentUser()?.username || "";
  const pickWho = (u: string) => {
    if (u === me) {
      const nf = fltRef.current === "mine" ? "open" : "mine";
      changeWho("");
      changeFlt(nf); load(nf, 1, q, "");
      return;
    }
    const nw = who === u ? "" : u;
    changeWho(nw);
    if (nw && (fltRef.current === "mine" || fltRef.current === "done")) changeFlt("open");
    load(fltRef.current, 1, q, nw);
  };

  // ── chia mục theo ngày (list liền mạch với thứ tự backend: chưa xong =
  // created DESC, filter "xong" = done_at DESC → nhóm luôn liền khối) ──
  const secOf = (t: Task): string => {
    if (!today) return "";
    const ts = flt === "done" && t.done_at ? t.done_at : t.created_at;
    const d = new Date(ts * 1000);
    const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (ymd >= today) return "Hôm nay";
    const diff = Math.round((+new Date(today) - +new Date(ymd)) / 864e5);
    if (diff === 1) return "Hôm qua";
    if (diff <= 7) return "7 ngày qua";
    if (diff <= 30) return "30 ngày qua";
    return "Cũ hơn";
  };
  const rows: any[] = [];
  {
    let prev = "";
    for (const t of tasks) {
      const s = secOf(t);
      if (s && s !== prev) { rows.push(<li class="tk-sec" key={`sec-${s}`}>{s}</li>); prev = s; }
      rows.push(<TaskCard key={t.id} t={t} today={today} names={names} onToggle={toggle} />);
    }
  }

  return (
    <div class="tasks-page">
      {/* app-bar đã đề "Việc" — header trang chỉ còn slider view + nút thêm */}
      <div class="row space tk-head">
        <div class="view-slider" role="group">
          <button class={mode === "list" ? "vs-seg on" : "vs-seg"} onClick={() => setMode("list")} title="Danh sách"><Icon name="menu" size={15} /></button>
          <button class={mode === "cal" ? "vs-seg on" : "vs-seg"} onClick={() => setMode("cal")} title="Lịch"><Icon name="calendar" size={15} /></button>
        </div>
        <button class="btn small primary" onClick={() => setCreating(true)}><Icon name="plus" size={15} /> Thêm việc</button>
      </div>

      {mode === "list" && (
        <>
          <div class="tk-stats">
            {STAT.map((s) => (
              <button key={s.k} class={`tk-stat ${s.cls}` + (flt === s.k ? " on" : "")}
                onClick={() => {
                  // "Của tôi" = assignee=me sẵn — đang chọn avatar thì bỏ cho khỏi chồng
                  if (s.k === "mine" && whoRef.current) changeWho("");
                  changeFlt(s.k); load(s.k, 1);
                }}>
                <span class="tk-stat-n">{counts ? counts[s.c] : "–"}</span>
                <span class="tk-stat-l"><Icon name={s.icon} size={12} /> {s.t}</span>
              </button>
            ))}
          </div>
          {Object.keys(names).length > 0 && (
            <div class="tk-people">
              {Object.entries(names).sort((a, b) => a[1].localeCompare(b[1], "vi")).map(([u, n]) => {
                // 2 màu: ĐỎ còn việc chưa xong / XANH hết việc; trong vòng = SỐ việc
                const nOpen = openBy[u] || 0;
                const c = nOpen > 0 ? "var(--danger)" : "var(--ok)";
                const on = who === u || (u === me && flt === "mine");
                return (
                  <button key={u} class={"tk-person" + (on ? " on" : "")} onClick={() => pickWho(u)}>
                    <span class="tk-person-a" style={{ background: c, boxShadow: on ? `0 0 0 2px var(--card), 0 0 0 4px ${c}` : "none" }}>{nOpen}</span>
                    <span class="tk-person-n" style={on ? { color: c } : undefined}>{n}</span>
                  </button>
                );
              })}
            </div>
          )}
          <div class="search-row">
            <SearchBar value={q} onInput={setQ} placeholder="Tìm việc, đơn, người làm…" />
          </div>
          <div class="chips tk-kinds">
            {KIND.map((f) => (
              <button key={f.k} class={"chip" + (flt === f.k ? " active" : "")}
                onClick={() => { changeFlt(f.k); load(f.k, 1); }}>
                {f.t}{counts ? <span class="chip-n">{counts[f.c]}</span> : null}
              </button>
            ))}
          </div>
          <FilterActiveBar
            parts={[flt !== "open" && (FLT.find((f) => f.k === flt)?.t || flt),
              who && `Việc của ${names[who] || who}`, q.trim() && `“${q.trim()}”`]}
            count={tasks.length}
            onClear={() => { setQ(""); changeWho(""); changeFlt("open"); load("open", 1, "", ""); }} />
          {loading && !tasks.length ? <SkeletonList rows={5} /> : null}
          {!loading && !tasks.length ? <EmptyState>Không có việc nào</EmptyState> : null}
          <ul class="task-list">{rows}</ul>
          {page < totalPages && <div ref={moreRef} class="tk-more-sentinel">{loading ? "Đang tải…" : ""}</div>}
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
