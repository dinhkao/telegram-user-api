// Khách hàng — KPI 3 ô (tổng/đang nợ/tổng nợ — chạm Đang nợ = lọc + sort nợ),
// tìm kiếm, card khách (avatar màu + nợ nổi bật + lần đặt gần nhất), infinite
// scroll. GET /api/customers?search=&sort=&owing=&page= (+stats ở trang 1).
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, createCustomer } from "../api";
import { money, fmtTime } from "../format";
import { onRealtime } from "../realtime";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { SearchBar, FilterActiveBar } from "../ui/SearchBar";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { avaColor } from "../ui/avatar";

const PAGE_SIZE = 30;
type CustStats = { total: number; owing: number; debt_sum: number };

// Cache toàn bộ list đã tải (module scope) → quay lại giữ nguyên list + vị trí cuộn
// (hệ cuộn trung tâm main.tsx khôi phục ngay, khỏi refetch/nhảy trang).
let custCache: {
  customers: any[]; page: number; totalPages: number; search: string;
  owing: boolean; stats: CustStats | null;
} | null = null;

// FIX realtime khi trang ĐANG UNMOUNT: đánh dấu "bẩn" nếu khách/công nợ đổi lúc vắng
// mặt → mount lại VÁ TẠI CHỖ (refreshMerge) thay vì hiện cache cũ. KHÔNG bỏ cache nên
// giữ nguyên list đã tải + vị trí cuộn. Riêng customer_changed KHÔNG key (= đổi cấu
// trúc: xoá khách) → BỎ cache hẳn (vá tại chỗ không gỡ được khách đã xoá).
let custDirty = false;
const custDirtyKeys = new Set<string>();   // khách đổi LÚC VẮNG MẶT → remount vá từng con
onRealtime((e) => {
  if (e.type === "customer_changed" && !(e as any).key) { custCache = null; return; }
  if (e.type === "customer_changed" && (e as any).key) custDirtyKeys.add(String((e as any).key));
  if (e.type === "customer_changed" || e.type === "order_changed" || e.type === "orders_changed" || e.type === "resync") custDirty = true;
});

export function Customers() {
  const c0 = custCache;
  const [search, setSearch] = useState(c0?.search || "");
  const [customers, setCustomers] = useState<any[]>(c0?.customers || []);
  const [stats, setStats] = useState<CustStats | null>(c0?.stats || null);
  const [owing, setOwing] = useState(c0?.owing || false);   // lọc ĐANG NỢ (KPI tile)
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [page, setPage] = useState(c0?.page || 1);
  const [totalPages, setTotalPages] = useState(c0?.totalPages || 1);
  const reqSeq = useRef(0);
  const sentinel = useRef<HTMLDivElement>(null);
  const st = useRef({ page: 1, totalPages: 1, loading: false, search: "", owing: false });
  st.current = { page, totalPages, loading, search, owing };
  const snap = useRef<any>(null);
  snap.current = { customers, page, totalPages, search, owing, stats };

  // đang nợ → sort nợ nhiều nhất trước; bình thường → hoạt động gần nhất trước
  const qUrl = (p: number, q: string, ow: boolean) =>
    `/api/customers?search=${encodeURIComponent(q)}&limit=${PAGE_SIZE}&page=${p}&sort=${ow ? "debt" : "recent"}${ow ? "&owing=1" : ""}`;

  const load = async (p: number, q: string, append: boolean, ow = st.current.owing) => {
    const seq = ++reqSeq.current;
    setLoading(true);
    setErr("");
    try {
      const r = await getJSON(qUrl(p, q, ow), { cache: false });
      if (seq !== reqSeq.current) return;
      setTotalPages(r.total_pages || 1);
      if (r.stats) setStats(r.stats);
      setCustomers((prev) => (append ? [...prev, ...(r.customers || [])] : r.customers || []));
    } catch (ex: any) {
      if (seq === reqSeq.current) setErr(ex.message);
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (custCache) {   // quay lại → state đã dựng từ cache (đủ cao cho hệ cuộn khôi phục)
      if (custDirty) { custDirty = false; refreshMerge(); }   // đổi lúc vắng mặt → vá tại chỗ (giữ cuộn)
      // khách đổi lúc vắng mặt NGOÀI page 1 (vd sửa nợ từ trang chi tiết) → vá từng con
      custDirtyKeys.forEach((k) => patchOne(k));
      custDirtyKeys.clear();
      return;
    }
    load(1, "", false);
  }, []);
  // Lưu snapshot khi rời trang
  useEffect(() => () => { if (snap.current?.customers?.length) custCache = { ...snap.current }; }, []);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        const { page: p, totalPages: tp, loading: ld, search: q } = st.current;
        if (ld || p >= tp) return;
        const next = p + 1;
        setPage(next);
        load(next, q, true);
      },
      { rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Realtime: cập nhật công nợ/khách MÀ KHÔNG co danh sách về trang 1. Lấy trang 1 mới
  // rồi VÁ tại chỗ theo key (giữ nguyên các trang đã cuộn + vị trí), chèn khách mới lên đầu.
  const refreshMerge = async () => {
    try {
      const r = await getJSON(qUrl(1, st.current.search, st.current.owing), { cache: false });
      const fresh: any[] = r.customers || [];
      if (r.stats) setStats(r.stats);
      const byKey = new Map(fresh.map((c) => [c.key, c]));
      setCustomers((prev) => {
        const seen = new Set(prev.map((c) => c.key));
        const patched = prev.map((c) => byKey.get(c.key) || c);          // cập nhật tại chỗ
        const added = fresh.filter((c) => !seen.has(c.key));             // khách mới → lên đầu
        return added.length ? [...added, ...patched] : patched;
      });
    } catch { /* im lặng */ }
  };

  const toggleOwing = () => {
    const ow = !owing;
    setOwing(ow);
    setPage(1);
    load(1, st.current.search, false, ow);
  };
  // Vá 1 khách theo key — hoạt động cả khi khách KHÔNG nằm trong page 1 hiện tại
  // (vd đang lọc Đang nợ mà khách vừa trả hết); 404 = đã xoá → gỡ khỏi list.
  const patchOne = async (key: string) => {
    try {
      const c = await getJSON(`/api/customers/${encodeURIComponent(key)}`, { cache: false });
      setCustomers((prev) => prev.map((x) => (x.key === key ? { ...x, ...c.customer } : x)));
    } catch {
      setCustomers((prev) => prev.filter((x) => x.key !== key));
    }
  };
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "customer_changed") {
        const k = (e as any).key;
        if (!k) {   // đổi cấu trúc (xoá khách) → tải lại hẳn trang 1
          clearTimeout(t);
          t = setTimeout(() => { setPage(1); load(1, st.current.search, false); }, 200);
          return;
        }
        patchOne(String(k));
      }
      if (e.type === "resync" || e.type === "order_changed" || e.type === "orders_changed" || e.type === "customer_changed") {
        clearTimeout(t);
        t = setTimeout(refreshMerge, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const onSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    if (q.length === 1) return;
    load(1, q, false);
  };

  // Tạo khách mới
  const [creating, setCreating] = useState(false);
  usePopupBack(creating, () => setCreating(false));
  useScrollLock(creating);   // khoá cuộn nền khi modal tạo khách mở
  const [nName, setNName] = useState("");
  const [nPhone, setNPhone] = useState("");
  const [nAddr, setNAddr] = useState("");
  const [saving, setSaving] = useState(false);
  const submitNew = async () => {
    const name = nName.trim();
    if (!name) return;
    setSaving(true);
    try {
      const c = await createCustomer({ name, contactNumber: nPhone.trim(), address: nAddr.trim() });
      toast(`✅ Đã tạo khách: ${c.name}`, "ok");
      setCreating(false); setNName(""); setNPhone(""); setNAddr("");
      window.location.hash = `#/khach/${encodeURIComponent(c.key)}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo khách", "err");
    } finally { setSaving(false); }
  };

  return (
    <div>
      <header class="topbar cust-topbar">
        <SearchBar value={search} onInput={onSearch} placeholder="Tìm khách hàng…" />
        <button class="btn primary cust-add" onClick={() => setCreating(true)} title="Tạo khách mới"><Icon name="plus" size={16} /></button>
      </header>
      {/* chips lọc kiểu dashboard Đơn — Đang nợ = khách còn nợ, sort nợ nhiều nhất trước */}
      <div class="chips">
        <button class={!owing ? "chip active" : "chip"} onClick={() => owing && toggleOwing()}>
          Tất cả {stats ? `(${stats.total})` : ""}
        </button>
        <button class={owing ? "chip active" : "chip"} onClick={() => !owing && toggleOwing()}>
          Đang nợ {stats ? `(${stats.owing})` : ""}
        </button>
      </div>
      <FilterActiveBar
        parts={[owing && "Đang nợ (nợ nhiều nhất trước)", search.trim() && `“${search.trim()}”`]}
        count={customers.length}
        onClear={() => { setSearch(""); setOwing(false); setPage(1); load(1, "", false, false); }} />

      {creating && (
        <div class="modal-overlay" onClick={saving ? undefined : () => setCreating(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="plus" size={18} /> Tạo khách hàng mới</div>
            <input class="cust-in" placeholder="Tên khách (bắt buộc)" value={nName} autofocus
              onInput={(e: any) => setNName(e.target.value)}
              onKeyDown={(e: any) => { if (e.key === "Enter" && nName.trim()) submitNew(); }} />
            <input class="cust-in" placeholder="Số điện thoại (tuỳ chọn)" inputMode="tel" value={nPhone}
              onInput={(e: any) => setNPhone(e.target.value)} />
            <input class="cust-in" placeholder="Địa chỉ (tuỳ chọn)" value={nAddr}
              onInput={(e: any) => setNAddr(e.target.value)} />
            <p class="muted small">Tạo trên KiotViet + mở topic khách. Có thể thêm bảng giá riêng sau.</p>
            <button class="btn primary block" disabled={saving || !nName.trim()} onClick={submitNew}>
              {saving ? "Đang tạo…" : "Tạo khách"}
            </button>
            {!saving && <button class="btn" onClick={() => setCreating(false)}>Huỷ</button>}
          </div>
        </div>
      )}
      {err && <ErrorState msg={err} onRetry={() => load(1, st.current.search, false)} />}
      <ul class="cust-list">
        {customers.map((c) => {
          const debt = c.debt != null ? Number(c.debt) || 0 : null;
          return (
            <li key={c.key}>
              <a class="cust-card" href={`#/khach/${encodeURIComponent(c.key)}`}>
                <span class="cu-ava" style={{ background: avaColor(c.name || c.key) }}>{(c.name || c.key)[0]}</span>
                <span class="cu-main">
                  <b class="cu-name">{c.name}</b>
                  <span class="cu-meta">
                    {c.kh_id ? `KV ${c.kh_id}` : c.key}
                    {c.last_order_at ? ` · đặt ${fmtTime(c.last_order_at)}` : ""}
                  </span>
                </span>
                <span class="cu-right">
                  {debt != null && (debt > 0
                    ? <b class="cu-debt">{money(debt)}</b>
                    : <span class="cu-clean"><Icon name="check" size={12} /> Sạch nợ</span>)}
                  <Icon name="chevronRight" size={16} class="cu-chev" />
                </span>
              </a>
            </li>
          );
        })}
      </ul>
      <div ref={sentinel} class="io-sentinel" />
      {loading && <Loading />}
      {!loading && !customers.length && !err && <EmptyState icon="👤">Không thấy khách</EmptyState>}
      {!loading && page >= totalPages && customers.length > 0 && (
        <p class="muted center small">Hết danh sách ({customers.length} khách)</p>
      )}
    </div>
  );
}
