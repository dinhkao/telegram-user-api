// Chi tiết PHIẾU KIỂM KHO ĐẬU (#/kho-dau/kiem/:id) — nháp: từng dòng đậu có ô đếm
// kép HOẶC ô tổng số (chọn "Cách nhập" đầu danh sách, nhớ theo máy ở localStorage
// `bean_stocktake_mode`; BeanStocktakeLine tự lưu khi rời ô), thanh tóm tắt thừa/thiếu, cảnh báo "sổ
// đã đổi" + nút Đồng bộ sổ, nút CHỐT (sinh phiếu điều chỉnh) và Huỷ (văn phòng).
// Đã chốt/huỷ: bảng chỉ đọc + link phiếu điều chỉnh. Ảnh + trao đổi + lịch sử scope
// 'bean_stocktake'. Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  BEAN_STOCKTAKE_STATUS_LABEL, completeBeanStocktake, countBeanStocktake, getBeanStocktake,
  isOffice, resyncBeanStocktake, soVN, voidBeanStocktake, type BeanStocktake,
} from "../api";
import { BeanStocktakeLine } from "../detail/BeanStocktakeLine";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { Images } from "../detail/Images";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, promptDialog, toast } from "../ui/feedback";
import { ErrorState, Loading } from "../ui/states";
import { StocktakeSummaryText } from "./BeanStocktakes";

const MODE_KEY = "bean_stocktake_mode";   // "bulk" (kiện + lẻ) | "total" (gõ thẳng tổng)
const readMode = (): "bulk" | "total" => {
  try { return localStorage.getItem(MODE_KEY) === "total" ? "total" : "bulk"; } catch { return "bulk"; }
};

export function BeanStocktakeDetail({ id }: { id: string }) {
  const [st, setSt] = useState<BeanStocktake | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [onlyUncounted, setOnlyUncounted] = useState(false);
  const [mode, setModeState] = useState<"bulk" | "total">(readMode);
  const setMode = (m: "bulk" | "total") => {
    setModeState(m);
    try { localStorage.setItem(MODE_KEY, m); } catch { /* private mode */ }
  };
  const office = isOffice();

  const load = () => getBeanStocktake(id)
    .then((s) => { setSt(s); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải phiếu kiểm"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), [id]);

  const save = async (bean_id: number, d: { bulk: string; loose: string; unit_id: number | null }) => {
    try {
      const s = await countBeanStocktake(Number(id), [{ bean_id, bulk: d.bulk, loose: d.loose, unit_id: d.unit_id }]);
      setSt(s);
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu số đếm", "err");
    }
  };

  const resync = async () => {
    if (!(await confirmDialog(
      "Đồng bộ sổ sách theo tồn HIỆN TẠI? Số đã đếm giữ nguyên; chênh lệch sẽ tính lại theo sổ mới.",
      { okLabel: "Đồng bộ sổ" }))) return;
    setBusy(true);
    try { setSt(await resyncBeanStocktake(Number(id))); toast("Đã đồng bộ sổ", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi đồng bộ", "err"); }
    finally { setBusy(false); }
  };

  const complete = async () => {
    if (!st) return;
    const s = st.summary;
    const lines = [
      `Chốt kiểm kho ${st.place_name}?`,
      s.uncounted ? `${s.uncounted} dòng chưa đếm sẽ BỎ QUA (không đụng tồn).` : "",
      s.over || s.short
        ? `Sinh 1 phiếu điều chỉnh: ${s.over ? `thừa ${s.over} dòng (+${soVN(s.sum_over)})` : ""}${s.over && s.short ? ", " : ""}${s.short ? `thiếu ${s.short} dòng (−${soVN(Math.abs(s.sum_short))})` : ""}.`
        : "Mọi dòng khớp sổ — chốt mà không sinh phiếu điều chỉnh.",
    ].filter(Boolean).join("\n");
    const note = await promptDialog(lines, { placeholder: "Ghi chú cho phiếu điều chỉnh (tuỳ chọn)", okLabel: "Chốt kiểm kho" });
    if (note === null) return;
    setBusy(true);
    try {
      const r = await completeBeanStocktake(Number(id), note);
      setSt(r);
      toast(r.slip_id ? `Đã chốt — phiếu điều chỉnh #${r.slip_id}` : "Đã chốt — khớp sổ, không điều chỉnh", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi chốt", "err"); }
    finally { setBusy(false); }
  };

  const voidIt = async () => {
    if (!(await confirmDialog("Huỷ phiếu kiểm này? Số đã đếm sẽ bỏ, tồn kho KHÔNG đổi.",
      { danger: true, okLabel: "Huỷ phiếu kiểm" }))) return;
    setBusy(true);
    try { setSt(await voidBeanStocktake(Number(id))); toast("Đã huỷ phiếu kiểm", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi huỷ", "err"); }
    finally { setBusy(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!st) return <Loading />;
  const draft = st.status === "draft";
  const items = draft && onlyUncounted ? st.items.filter((i) => i.counted_qty == null) : st.items;
  // Chọn cách nhập chỉ có nghĩa khi có loại đậu khai đơn vị quy đổi (không thì 1 ô sẵn rồi)
  const anyUnits = st.items.some((i) => (i.units || []).length > 0);

  return (
    <div class="bean-detail bst-detail">
      <PageHead fallback="#/kho-dau/kiem"
        title={<>Kiểm kho {st.place_name} <span class="muted small">#{st.id}</span></>}
        sub={<><span class={"bst-status s-" + st.status}>{BEAN_STOCKTAKE_STATUS_LABEL[st.status]}</span>
          {" · "}<StocktakeSummaryText s={st.summary} /></>}
        right={draft && office ? (
          <button class="btn small danger" disabled={busy} title="Huỷ phiếu kiểm" onClick={voidIt}>
            <Icon name="trash" size={15} />
          </button>
        ) : undefined} />

      <div class="bean-meta muted small">
        Mở bởi {st.created_by || "—"} · {fmtDateTimeVN(st.created_at)}
        {st.completed_at ? <> · chốt bởi <b>{st.completed_by}</b> {fmtDateTimeVN(st.completed_at)}</> : null}
        {st.voided_at ? <> · huỷ bởi <b>{st.voided_by}</b> {fmtDateTimeVN(st.voided_at)}</> : null}
      </div>
      {st.note ? <div class="bean-note">“{st.note}”</div> : null}

      {st.status === "done" && (
        <div class="bean-hint">
          {st.slip ? (
            <>Đã sinh <a href={`#/kho-dau/phieu/${st.slip.id}`}><b>phiếu điều chỉnh #{st.slip.id}</b></a>
              {" "}({st.slip.lines} dòng, ngày {st.slip.ymd}).</>
          ) : st.slip_id ? <>Phiếu điều chỉnh #{st.slip_id} đã bị xoá — tồn đã hoàn về trước khi chốt.</>
            : <>Mọi dòng đếm khớp sổ — không sinh phiếu điều chỉnh.</>}
        </div>
      )}

      {draft && st.stale_count > 0 && (
        <div class="bean-hint bst-stale">
          <b>{st.stale_count} dòng</b> có sổ sách đã đổi từ lúc bắt đầu kiểm (kho có nhập/xuất
          sau đó). Chốt vẫn áp đúng <b>chênh lệch đã đếm</b>; muốn so với tồn hiện tại thì
          {" "}<button class="bean-link" disabled={busy} onClick={resync}>Đồng bộ sổ</button>.
        </div>
      )}

      {draft ? (
        <>
          <div class="ie-head">
            Đếm từng loại đậu
            <label class="bst-toggle small">
              <input type="checkbox" checked={onlyUncounted}
                onChange={(e: any) => setOnlyUncounted(e.target.checked)} /> chỉ dòng chưa đếm
            </label>
          </div>
          {anyUnits && (
            <div class="bst-mode row">
              <span class="muted small">Cách nhập:</span>
              <div class="seg">
                <button class={"seg-btn" + (mode === "bulk" ? " active" : "")} onClick={() => setMode("bulk")}>Kiện + lẻ</button>
                <button class={"seg-btn" + (mode === "total" ? " active" : "")} onClick={() => setMode("total")}>Tổng số</button>
              </div>
              <span class="muted small bst-mode-hint">
                {mode === "total" ? "Gõ thẳng số hiện có theo đơn vị gốc (vd cân được 112 kg)." : "Đếm số kiện rồi cộng phần lẻ."}
              </span>
            </div>
          )}
          {items.length ? items.map((it) => (
            <BeanStocktakeLine key={it.bean_id} item={it} readonly={false} totalMode={mode === "total"} onSave={save} />
          )) : <div class="muted small center">Đã đếm hết mọi dòng.</div>}
          <div class="bst-actions">
            <button class="btn" disabled={busy} onClick={resync} title="Đặt lại sổ theo tồn hiện tại, giữ số đếm">
              <Icon name="refresh" size={15} /> Đồng bộ sổ
            </button>
            <button class="btn primary" disabled={busy || !st.summary.counted} onClick={complete}>
              <Icon name="check" size={15} /> Chốt kiểm kho
            </button>
          </div>
        </>
      ) : (
        <table class="bean-table">
          <thead><tr><th>Loại đậu</th><th class="num">Sổ</th><th class="num">Đếm</th><th class="num">Lệch</th></tr></thead>
          <tbody>
            {st.items.map((it) => <BeanStocktakeLine key={it.bean_id} item={it} readonly onSave={save} />)}
          </tbody>
        </table>
      )}

      <Images base={`/api/media/bean_stocktake/${st.id}`} />
      <Comments base={`/api/media/bean_stocktake/${st.id}`} />
      <History base={`/api/media/bean_stocktake/${st.id}`} />

      <a class="btn bean-more" href={`#/kho-dau/kho/${st.place_id}`}><Icon name="box" size={15} /> Xem kho {st.place_name}</a>
    </div>
  );
}
