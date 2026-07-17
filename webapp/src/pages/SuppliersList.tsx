// Dashboard NHÀ CUNG CẤP (#/ncc) — mọi NCC + thống kê (số phiếu nhập, tổng tiền,
// lần nhập cuối). Card → #/ncc/:id. Tạo NCC = popup (văn phòng). 100% local.
// Realtime: supplier_changed/resync → tải lại. Cache module — quay lại tức thì.
import { useEffect, useState } from "preact/hooks";
import { createSupplier, listSuppliers, soVN, type Supplier } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { SearchBar } from "../ui/SearchBar";
import { SkeletonList, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";

let supCache: Supplier[] | null = null;
onRealtime((e) => {
  if (e.type === "supplier_changed" || e.type === "purchase_changed" || e.type === "resync") supCache = null;
});

let memQ = "";

function CreateSupplierModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);
  const submit = async () => {
    if (!name.trim()) return toast("Nhập tên nhà cung cấp", "info");
    setBusy(true);
    try {
      const s = await createSupplier({ name: name.trim(), phone: phone.trim(), address: address.trim(), note: note.trim() });
      toast(`Đã tạo NCC "${s.name}"`, "ok");
      onCreated();
      onClose();
      window.location.hash = `#/ncc/${s.id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo NCC", "err");
    } finally { setBusy(false); }
  };
  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet ret-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="users" size={16} /> Nhà cung cấp mới</div>
        <input type="text" placeholder="Tên nhà cung cấp *" value={name} onInput={(e) => setName((e.target as HTMLInputElement).value)} />
        <input type="tel" placeholder="Số điện thoại" value={phone} onInput={(e) => setPhone((e.target as HTMLInputElement).value)} />
        <input type="text" placeholder="Địa chỉ" value={address} onInput={(e) => setAddress((e.target as HTMLInputElement).value)} />
        <input type="text" placeholder="Ghi chú" value={note} onInput={(e) => setNote((e.target as HTMLInputElement).value)} />
        <div class="row">
          <button class="btn" onClick={onClose}>Huỷ</button>
          <button class="btn primary" disabled={busy || !name.trim()} onClick={submit}>
            {busy ? "Đang tạo…" : "Tạo NCC"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function SuppliersList() {
  const [rows, setRows] = useState<Supplier[]>(supCache || []);
  const [q, setQ] = useState(memQ);
  useEffect(() => { memQ = q; }, [q]);
  const [loading, setLoading] = useState(!supCache);
  const [err, setErr] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const load = async () => {
    try {
      const r = await listSuppliers();
      supCache = r;
      setRows(r);
      setErr("");
    } catch (e: any) {
      // Lỗi nền khi đã có dữ liệu → giữ cache im lặng; chưa có gì thì hiện ErrorState
      setErr(e?.message || "Lỗi tải nhà cung cấp");
    } finally { setLoading(false); }
  };
  useEffect(() => { if (!supCache) load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "supplier_changed" || e.type === "purchase_changed" || e.type === "resync") load();
  }), []);

  const fq = foldVN(q.trim());
  const visible = !fq ? rows : rows.filter((s) =>
    foldVN(`${s.name} ${s.phone || ""} ${s.address || ""} ${s.note || ""}`).includes(fq));

  // Tạo NCC mở cho MỌI người dùng (2026-07-17, cùng đợt mở tạo phiếu nhập)
  const openCreate = () => setCreateOpen(true);

  return (
    <div class="ret-list">
      <div class="ret-toolbar">
        <SearchBar value={q} onInput={setQ} placeholder="Tìm tên, SĐT, địa chỉ…" />
        <button class="btn primary" onClick={openCreate}>
          <Icon name="plus" size={16} /> Tạo NCC
        </button>
      </div>
      {createOpen && <CreateSupplierModal onClose={() => setCreateOpen(false)} onCreated={load} />}
      {loading && !rows.length && <SkeletonList />}
      {!loading && !rows.length && err && <ErrorState msg={err} onRetry={load} />}
      {!loading && !rows.length && !err && <EmptyState>Chưa có nhà cung cấp nào.</EmptyState>}
      {!loading && rows.length > 0 && !visible.length && <EmptyState>Không có NCC khớp "{q}".</EmptyState>}
      {visible.map((s) => (
        <a class="ret-card sup-card" href={`#/ncc/${s.id}`} key={s.id}>
          <div class="ret-card-top">
            <span class="ret-cust">{s.name}</span>
            {(s.tong_tien || 0) > 0 && <span class="pur-amt">{soVN(s.tong_tien || 0)}</span>}
          </div>
          <div class="ret-card-sub muted small">
            {[s.phone, s.address].filter(Boolean).join(" · ")}
            {s.so_phieu ? ` · ${s.so_phieu} phiếu nhập` : " · chưa có phiếu nhập"}
            {s.last_at ? ` · lần cuối ${s.last_at.slice(8, 10)}/${s.last_at.slice(5, 7)}` : ""}
          </div>
          {s.note && <div class="ret-card-note"><Icon name="note" size={12} /> {s.note}</div>}
        </a>
      ))}
      {visible.length > 0 && <div class="muted small list-count">{visible.length} nhà cung cấp</div>}
    </div>
  );
}
