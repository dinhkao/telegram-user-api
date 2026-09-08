// Danh sách PHIẾU KIỂM KHO ĐẬU (#/kho-dau/kiem) — nháp lên đầu, rồi mới → cũ; chip lọc
// trạng thái; nút "Bắt đầu kiểm kho" chọn kho → mở phiếu (kho đang có nháp → nhảy
// thẳng vào nháp đó). Card → #/kho-dau/kiem/:id. Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  BEAN_STOCKTAKE_STATUS_LABEL, createBeanStocktake, getBeanBoard, listBeanStocktakes, soVN,
  type BeanPlace, type BeanStocktakeRow, type BeanStocktakeStatus,
} from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { toast } from "../ui/feedback";
import { EmptyState, ErrorState, LoadingInline, SkeletonList } from "../ui/states";

/** Mở phiếu kiểm cho kho: đã có nháp → vào nháp; chưa → tạo mới. Dùng chung với trang kho. */
export async function openBeanStocktake(placeId: number): Promise<void> {
  const r = await listBeanStocktakes({ place_id: placeId, status: "draft" });
  if (r.stocktakes[0]) {
    toast(`Kho này đang có phiếu kiểm #${r.stocktakes[0].id} — mở tiếp`, "info");
    window.location.hash = `#/kho-dau/kiem/${r.stocktakes[0].id}`;
    return;
  }
  const st = await createBeanStocktake(placeId);
  toast("Đã mở phiếu kiểm kho — bắt đầu đếm", "ok");
  window.location.hash = `#/kho-dau/kiem/${st.id}`;
}

export function StocktakeSummaryText({ s }: { s: BeanStocktakeRow["summary"] }) {
  if (!s.counted) return <span class="muted">chưa đếm dòng nào / {s.total}</span>;
  return (
    <>
      đã đếm {s.counted}/{s.total}
      {s.over ? <span class="t-ok"> · thừa {s.over} (+{soVN(s.sum_over)})</span> : null}
      {s.short ? <span class="t-danger"> · thiếu {s.short} (−{soVN(Math.abs(s.sum_short))})</span> : null}
      {s.match ? <span class="muted"> · khớp {s.match}</span> : null}
    </>
  );
}

export function BeanStocktakes() {
  const [status, setStatus] = useState<BeanStocktakeStatus | "">("");
  const [rows, setRows] = useState<BeanStocktakeRow[] | null>(null);
  const [places, setPlaces] = useState<BeanPlace[]>([]);
  const [placeId, setPlaceId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState("");

  const load = (p = 1) => {
    setBusy(true);
    return listBeanStocktakes({ status: status || undefined, page: p })
      .then((r) => {
        setRows((prev) => (p === 1 || !prev ? r.stocktakes : [...prev, ...r.stocktakes]));
        setPage(r.page); setPages(r.total_pages); setTotal(r.total); setErr("");
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải phiếu kiểm"))
      .finally(() => setBusy(false));
  };
  useEffect(() => { setRows(null); load(1); }, [status]);
  useEffect(() => {
    getBeanBoard().then((d) => { setPlaces(d.places); setPlaceId((v) => v ?? (d.places[0]?.id ?? null)); })
      .catch(() => {});
  }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load(1);
  }), [status]);

  const start = async () => {
    if (!placeId) return toast("Chọn kho cần kiểm", "info");
    setStarting(true);
    try { await openBeanStocktake(placeId); }
    catch (e: any) { toast(e?.message || "Lỗi mở phiếu kiểm", "err"); }
    finally { setStarting(false); }
  };

  return (
    <div class="bean-slips">
      <PageHead fallback="#/kho-dau" title={<><Icon name="clipboard" size={18} /> Kiểm kho đậu</>}
        sub={`${total} phiếu kiểm`} />

      <div class="bst-start">
        <div class="ie-head">Bắt đầu kiểm kho</div>
        <div class="bean-form-row">
          <SelectPopup value={placeId ?? ""} title="Chọn kho cần kiểm"
            options={places.map((p) => ({ value: p.id, label: p.name, sub: p.note || undefined }))}
            onChange={(v) => setPlaceId(Number(v))} placeholder="Chọn kho…" searchable />
          <button class="btn primary" disabled={starting || !placeId} onClick={start}>
            {starting ? "…" : <><Icon name="plus" size={15} /> Kiểm</>}
          </button>
        </div>
        <div class="muted small">Hệ thống chụp sổ sách lúc này; bạn đếm thực tế rồi chốt — lệch bao nhiêu
          sinh 1 phiếu điều chỉnh đúng bấy nhiêu.</div>
      </div>

      <div class="chips">
        <button class={"chip" + (status === "" ? " active" : "")} onClick={() => setStatus("")}>Tất cả</button>
        {(["draft", "done", "voided"] as BeanStocktakeStatus[]).map((k) => (
          <button class={"chip" + (status === k ? " active" : "")} key={k} onClick={() => setStatus(k)}>
            {BEAN_STOCKTAKE_STATUS_LABEL[k]}
          </button>
        ))}
      </div>

      {!rows && !err && <SkeletonList />}
      {err && !rows?.length && <ErrorState msg={err} onRetry={() => load(1)} />}
      {rows && !rows.length && !err && <EmptyState>Chưa có phiếu kiểm nào.</EmptyState>}

      {rows?.map((r) => (
        <a class={"bean-slip-card bst-card s-" + r.status} href={`#/kho-dau/kiem/${r.id}`} key={r.id}>
          <div class="bean-slip-top">
            <span class="bean-slip-kind"><Icon name="clipboard" size={14} /> {r.place_name}
              <span class="muted small"> #{r.id}</span></span>
            <span class={"bst-status s-" + r.status}>{BEAN_STOCKTAKE_STATUS_LABEL[r.status]}</span>
          </div>
          <div class="bean-slip-sub muted small">
            <StocktakeSummaryText s={r.summary} />
            {r.status === "done" && r.slip_id ? <span> · phiếu điều chỉnh #{r.slip_id}</span> : null}
            {r.status === "done" && !r.slip_id ? <span> · khớp sổ, không điều chỉnh</span> : null}
          </div>
          <div class="bean-slip-sub muted small">
            {r.created_by || "—"} · {fmtDateTimeVN(r.created_at)}
            {r.completed_at ? ` · chốt ${fmtDateTimeVN(r.completed_at)} (${r.completed_by})` : ""}
          </div>
        </a>
      ))}

      {busy && rows?.length ? <p class="muted small center"><LoadingInline /></p> : null}
      {rows && page < pages && !busy && (
        <button class="btn bean-more" onClick={() => load(page + 1)}>Xem thêm</button>
      )}
    </div>
  );
}
