// Sổ quỹ — GET /api/quy (phân trang 20/trang). Header: số dư + tổng thu/chi.
// Tạo phiếu thu/chi tay ở đầu. Phiếu nguồn 'order' (thanh toán tiền mặt) gắn link
// tới đơn, không xoá tay được. Realtime: quy_changed/resync → tải lại trang 1.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  listQuy,
  createQuy,
  deleteQuy,
  soVN,
  type QuyReceipt,
  type QuySummary,
} from "../api";
import { onRealtime } from "../realtime";
import { Loading, EmptyState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

type Filter = "all" | "thu" | "chi";

// Cache list đã tải → quay lại giữ nguyên (hệ cuộn khôi phục vị trí).
let quyCache: { receipts: QuyReceipt[]; page: number; totalPages: number; filter: Filter } | null = null;

export function QuyList() {
  const [receipts, setReceipts] = useState<QuyReceipt[]>([]);
  const [summary, setSummary] = useState<QuySummary>({ thu: 0, chi: 0, balance: 0, count: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>(quyCache?.filter || "all");
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState("");
  // Form tạo phiếu
  const [ftype, setFtype] = useState<"thu" | "chi">("thu");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const st = useRef({ page: 1, totalPages: 1, loading: false, filter });
  const sentinel = useRef<HTMLDivElement>(null);

  const load = async (page: number, append: boolean, f: Filter = st.current.filter) => {
    if (st.current.loading) return;
    st.current.loading = true;
    if (!append) setLoading(true);
    try {
      const r = await listQuy(page, f === "all" ? undefined : f);
      st.current.page = r.page;
      st.current.totalPages = r.total_pages;
      st.current.filter = f;
      setTotal(r.total);
      setSummary(r.summary);
      setReceipts((prev) => (append ? [...prev, ...r.receipts] : r.receipts));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải sổ quỹ");
    } finally {
      st.current.loading = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    if (quyCache) {
      setReceipts(quyCache.receipts);
      st.current.page = quyCache.page;
      st.current.totalPages = quyCache.totalPages;
      st.current.filter = quyCache.filter;
      // vẫn refresh summary + trang 1 nền cho số liệu mới
    }
    load(1, false);
  }, []);

  const recRef = useRef<QuyReceipt[]>([]);
  recRef.current = receipts;
  useEffect(() => () => {
    if (recRef.current.length)
      quyCache = { receipts: recRef.current, page: st.current.page, totalPages: st.current.totalPages, filter: st.current.filter };
  }, []);

  // Realtime
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "quy_changed" || e.type === "resync") load(1, false);
    });
  }, []);

  // Cuộn tải thêm
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        const { page, totalPages, loading: ld } = st.current;
        if (ld || page >= totalPages) return;
        load(page + 1, true);
      },
      { rootMargin: "300px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const changeFilter = (f: Filter) => {
    if (f === filter) return;
    setFilter(f);
    setReceipts([]);
    load(1, false, f);
  };

  const doCreate = async () => {
    const n = parseInt(amount.replace(/[.,\s]/g, ""), 10);
    if (!n || n <= 0) {
      toast("Nhập số tiền hợp lệ", "err");
      return;
    }
    setSaving(true);
    setErr("");
    try {
      await createQuy(ftype, n, note.trim());
      setAmount("");
      setNote("");
      toast(ftype === "thu" ? "Đã tạo phiếu thu" : "Đã tạo phiếu chi", "ok");
      // realtime quy_changed sẽ tải lại; vẫn load ngay cho chắc
      load(1, false);
    } catch (e: any) {
      setErr(e?.message || "Tạo phiếu thất bại");
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async (r: QuyReceipt) => {
    if (r.source === "order") {
      toast("Phiếu gắn đơn — xoá bằng cách xoá thanh toán trong đơn", "info");
      return;
    }
    if (!(await confirmDialog(`Xoá phiếu ${r.type === "thu" ? "thu" : "chi"} ${soVN(r.amount)}đ?`, { danger: true, okLabel: "Xoá" })))
      return;
    try {
      await deleteQuy(r.id);
      setReceipts((prev) => prev.filter((x) => x.id !== r.id));
      toast("Đã xoá", "ok");
      load(1, false);
    } catch (e: any) {
      toast(e?.message || "Xoá thất bại", "err");
    }
  };

  return (
    <div class="quy-list">
      {/* Header số dư */}
      <div class="quy-summary">
        <div class="quy-sum-balance">
          <div class="quy-sum-lbl">💼 Số dư quỹ</div>
          <div class={"quy-sum-val " + (summary.balance < 0 ? "neg" : "")}>{soVN(summary.balance)}đ</div>
        </div>
        <div class="quy-sum-row">
          <div class="quy-sum-cell thu"><span>Thu</span><b>+{soVN(summary.thu)}đ</b></div>
          <div class="quy-sum-cell chi"><span>Chi</span><b>−{soVN(summary.chi)}đ</b></div>
        </div>
      </div>

      {/* Form tạo phiếu */}
      <div class="quy-create">
        <div class="quy-type-toggle">
          <button class={ftype === "thu" ? "qt thu active" : "qt"} onClick={() => setFtype("thu")}>➕ Thu</button>
          <button class={ftype === "chi" ? "qt chi active" : "qt"} onClick={() => setFtype("chi")}>➖ Chi</button>
        </div>
        <input
          class="quy-input"
          type="tel"
          inputMode="numeric"
          placeholder="Số tiền"
          value={amount}
          onInput={(e: any) => setAmount(e.currentTarget.value)}
        />
        <input
          class="quy-input"
          type="text"
          placeholder="Ghi chú (lý do)"
          value={note}
          onInput={(e: any) => setNote(e.currentTarget.value)}
        />
        <button class="btn primary" disabled={saving} onClick={doCreate}>
          {saving ? "Đang lưu…" : ftype === "thu" ? "Lưu phiếu thu" : "Lưu phiếu chi"}
        </button>
      </div>

      {/* Filter */}
      <div class="quy-filter">
        {(["all", "thu", "chi"] as Filter[]).map((f) => (
          <button key={f} class={filter === f ? "qf active" : "qf"} onClick={() => changeFilter(f)}>
            {f === "all" ? "Tất cả" : f === "thu" ? "Thu" : "Chi"}
          </button>
        ))}
      </div>

      {err && <div class="error-banner">{err}</div>}
      {loading && !receipts.length && <Loading />}
      {!loading && !receipts.length && <EmptyState icon="💰">Chưa có phiếu quỹ nào.</EmptyState>}

      <div class="quy-cards">
        {groupByDay(receipts).map((g) => (
          <div class="quy-group" key={g.key}>
            <div class="quy-group-head">{g.label} <span class="muted small">({g.receipts.length})</span></div>
            {g.receipts.map((r) => <QuyRow key={r.id} r={r} onDelete={doDelete} />)}
          </div>
        ))}
      </div>

      <div ref={sentinel} style={{ height: "1px" }} />
      {receipts.length > 0 && (
        <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>
          {receipts.length}/{total} phiếu
        </div>
      )}
    </div>
  );
}

function QuyRow({ r, onDelete }: { r: QuyReceipt; onDelete: (r: QuyReceipt) => void }) {
  const thu = r.type === "thu";
  const time = (r.created_at || "").slice(11, 16);
  return (
    <div class={"quy-row " + (thu ? "thu" : "chi")}>
      <div class="quy-row-main">
        <div class="quy-row-top">
          <span class={"quy-amt " + (thu ? "thu" : "chi")}>{thu ? "+" : "−"}{soVN(r.amount)}đ</span>
          {r.source === "order" && r.order_thread_id != null && (
            <a class="quy-order-link" href={`#/order/${r.order_thread_id}`}>🧾 Đơn #{r.order_thread_id}</a>
          )}
          {time && <span class="quy-time muted small">🕒 {time}</span>}
        </div>
        {r.note && <div class="quy-note">{r.note}</div>}
        {(r.customer_name || r.created_by) && (
          <div class="muted small">
            {r.customer_name ? `👤 ${r.customer_name}` : ""}
            {r.customer_name && r.created_by ? " · " : ""}
            {r.created_by ? `✍️ ${r.created_by}` : ""}
          </div>
        )}
      </div>
      {r.source !== "order" && (
        <button class="quy-del" title="Xoá" onClick={() => onDelete(r)}>🗑️</button>
      )}
    </div>
  );
}

const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function groupByDay(receipts: QuyReceipt[]): { key: string; label: string; receipts: QuyReceipt[] }[] {
  const out: { key: string; label: string; receipts: QuyReceipt[] }[] = [];
  for (const r of receipts) {
    const key = r.date || "?"; // YYYY-MM-DD
    const last = out[out.length - 1];
    if (last && last.key === key) last.receipts.push(r);
    else out.push({ key, label: dayLabel(key), receipts: [r] });
  }
  return out;
}

function dayLabel(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  if (!y || !m || !d) return "Không rõ ngày";
  const date = new Date(y, m - 1, d);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  const wd = _WD[date.getDay()];
  const dm = `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`;
  if (diff === 0) return `Hôm nay · ${wd} ${dm}`;
  if (diff === 1) return `Hôm qua · ${wd} ${dm}`;
  return `${wd} · ${dm}/${y}`;
}
