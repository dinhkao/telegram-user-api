// Dashboard XUẤT HỦY (#/xuat-huy) — mọi phiếu hủy hàng, nhóm theo ngày. Card →
// #/xuat-huy/:id. Tạo phiếu = nút "Xuất hủy" ở trang chi tiết THÙNG (#/thung/:id)
// — hủy tại chỗ khi thấy hàng hư. Realtime: disposal_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { listDisposals, soVN, type DisposalSlip } from "../api";
import { dayKey, dayLabel, foldVN } from "../format";
import { onRealtime } from "../realtime";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState, ErrorState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

let dispCache: DisposalSlip[] | null = null;
onRealtime((e) => {
  if (e.type === "disposal_changed" || e.type === "resync") dispCache = null;
});

let memQ = "";

export function DisposalsList() {
  const [rows, setRows] = useState<DisposalSlip[]>(dispCache || []);
  const [q, setQ] = useState(memQ);
  useEffect(() => { memQ = q; }, [q]);
  const [loading, setLoading] = useState(!dispCache);
  const [err, setErr] = useState("");

  const load = () => listDisposals()
    .then((r) => { setRows(r); dispCache = r; setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải danh sách"))
    .finally(() => setLoading(false));
  useEffect(() => { if (!dispCache) load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "disposal_changed" || e.type === "resync") load();
  }), []);
  const rowsRef = useRef<DisposalSlip[]>([]);
  rowsRef.current = rows;
  useEffect(() => () => { if (rowsRef.current.length) dispCache = rowsRef.current; }, []);

  const fq = foldVN(q.trim());
  const visible = !fq ? rows : rows.filter((r) => foldVN(
    `${r.reason} ${(r.items || []).map((x) => `${x.product_code} ${x.box_code || ""}`).join(" ")} ${r.created_by || ""}`
  ).includes(fq));

  const groups: { key: string; items: DisposalSlip[] }[] = [];
  for (const r of visible) {
    const k = dayKey(r.created_at);
    const last = groups[groups.length - 1];
    if (last && last.key === k) last.items.push(r);
    else groups.push({ key: k, items: [r] });
  }

  return (
    <div class="ret-list">
      <div class="ret-toolbar">
        <SearchBar value={q} onInput={setQ} placeholder="Tìm lý do, SP, thùng…" />
        <a class="btn primary" href="#/kho"><Icon name="box" size={16} /> Chọn thùng</a>
      </div>
      <div class="muted small list-hint">
        Hủy hàng hư/hết hạn: mở thùng trong 📦 Kho → bấm "Xuất hủy". Tồn thùng trừ ngay, xoá phiếu (admin) sẽ hoàn lại.
      </div>
      {loading && !rows.length && <Loading />}
      {!loading && err && !rows.length && <ErrorState msg={err} onRetry={() => { setLoading(true); load(); }} />}
      {!loading && !err && !rows.length && <EmptyState>Chưa có phiếu xuất hủy nào.</EmptyState>}
      {!loading && rows.length > 0 && !visible.length && <EmptyState>Không có phiếu khớp "{q}".</EmptyState>}
      {groups.map((g) => (
        <div class="prod-group" key={g.key}>
          <div class="prod-group-head">{dayLabel(g.key)} <span class="muted small">({g.items.length})</span></div>
          {g.items.map((r) => (
            <a class="ret-card" href={`#/xuat-huy/${r.id}`} key={r.id}>
              <div class="ret-card-top">
                <span class="ret-cust"><Icon name="trash" size={14} /> {r.reason}</span>
                <span class="disp-amt">−{soVN(r.total_quantity)}</span>
              </div>
              <div class="ret-card-sub muted small">
                {r.box_less ? <span class="disp-boxless-tag">hàng trả</span> : null}
                {(r.items || []).map((x) => `${x.product_code} ×${soVN(x.quantity)}${x.box_id ? ` (thùng ${(x.box_code || "").split("-").pop()})` : ""}`).join(", ")}
                {r.created_by ? ` · ${r.created_by}` : ""}
                {r.created_at ? ` · ${r.created_at.slice(11, 16)}` : ""}
              </div>
            </a>
          ))}
        </div>
      ))}
      {visible.length > 0 && <div class="muted small list-count">{visible.length} phiếu</div>}
    </div>
  );
}
