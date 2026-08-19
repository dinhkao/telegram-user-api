// Danh sách PHIẾU KHO ĐẬU (#/kho-dau/phieu) — nhập/xuất/điều chỉnh, mới → cũ,
// nhóm theo ngày phiếu. Chip lọc theo loại phiếu; "Xem thêm" tải trang kế.
// Card (detail/BeanSlipRows) → #/kho-dau/phieu/:id. Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { listBeanSlips, BEAN_KIND_LABEL, type BeanSlip, type BeanSlipKind } from "../api";
import { BeanSlipCard } from "../detail/BeanSlipRows";
import { dayLabel } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, LoadingInline, SkeletonList } from "../ui/states";

export function BeanSlips() {
  const [kind, setKind] = useState<BeanSlipKind | "">("");
  const [slips, setSlips] = useState<BeanSlip[] | null>(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = (p = 1) => {
    setBusy(true);
    return listBeanSlips({ kind: kind || undefined, page: p })
      .then((r) => {
        setSlips((prev) => (p === 1 || !prev ? r.slips : [...prev, ...r.slips]));
        setPage(r.page); setPages(r.total_pages); setTotal(r.total); setErr("");
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"))
      .finally(() => setBusy(false));
  };
  useEffect(() => { setSlips(null); load(1); }, [kind]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load(1);
  }), [kind]);

  const groups: { key: string; items: BeanSlip[] }[] = [];
  for (const s of slips || []) {
    const last = groups[groups.length - 1];
    if (last && last.key === s.ymd) last.items.push(s);
    else groups.push({ key: s.ymd, items: [s] });
  }

  return (
    <div class="bean-slips">
      <PageHead fallback="#/kho-dau" title={<><Icon name="receipt" size={18} /> Phiếu kho đậu</>}
        sub={`${total} phiếu`}
        right={<a class="btn small primary" href="#/kho-dau/tao?kind=nhap"><Icon name="plus" size={15} /></a>} />

      <div class="chips">
        <button class={"chip" + (kind === "" ? " active" : "")} onClick={() => setKind("")}>Tất cả</button>
        {(["nhap", "xuat", "dieu_chinh"] as BeanSlipKind[]).map((k) => (
          <button class={"chip" + (kind === k ? " active" : "")} key={k} onClick={() => setKind(k)}>
            {BEAN_KIND_LABEL[k]}
          </button>
        ))}
      </div>

      {!slips && !err && <SkeletonList />}
      {err && !slips?.length && <ErrorState msg={err} onRetry={() => load(1)} />}
      {slips && !slips.length && !err && (
        <EmptyState>Chưa có phiếu nào. Bấm ➕ để tạo phiếu nhập.</EmptyState>
      )}

      {groups.map((g) => (
        <div class="prod-group" key={g.key}>
          <div class="prod-group-head">{dayLabel(g.key)} <span class="muted small">({g.items.length})</span></div>
          {g.items.map((s) => <BeanSlipCard slip={s} showDate={false} key={s.id} />)}
        </div>
      ))}

      {busy && slips?.length ? <p class="muted small center"><LoadingInline /></p> : null}
      {slips && page < pages && !busy && (
        <button class="btn bean-more" onClick={() => load(page + 1)}>Xem thêm</button>
      )}
    </div>
  );
}
