// Chi tiết phiếu TRẢ HÀNG (#/tra-hang/:id) — giống trang đơn: NHÁP sửa được →
// bấm 'Tạo HĐ KiotViet' mới trừ nợ (khoá sửa); ảnh + trao đổi + lịch sử thao tác
// dùng chung entity media scope 'return'. Xoá = admin (fade + toast; server chặn).
import { useEffect, useRef, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import {
  getReturn, deleteReturn, deleteReturnInvoice, updateReturn, invoiceReturn, searchProducts,
  currentUser, isOffice, soVN, type ReturnSlip,
} from "../api";
import { onRealtime } from "../realtime";
import { fmtDateTimeVN, parseMoney, parseQty } from "../format";
import { ReturnGoodsModal } from "../detail/ReturnGoodsModal";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string };

export function ReturnDetail({ id }: { id: string }) {
  const [r, setR] = useState<ReturnSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [note, setNote] = useState("");
  const [showGoods, setShowGoods] = useState(false);
  const autoOpened = useRef(false);
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();

  const load = () => getReturn(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  // Mở modal "Xử lý hàng trả" nếu vừa tạo phiếu và người dùng chọn "Xử lý ngay" (cờ session).
  useEffect(() => {
    if (!r || autoOpened.current) return;
    if (sessionStorage.getItem("rg_open") === String(id)) {
      sessionStorage.removeItem("rg_open");
      autoOpened.current = true;
      if (!r.goods_handled_at && office) setShowGoods(true);
    }
  }, [r]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const hit = e.type === "resync" || e.type === "customer_changed" ||
        (e.type === "return_changed" && e.id === String(id));
      if (hit) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!r) return <Loading />;
  const deleted = !!(r as any).deleted_at;
  const invoiced = !!r.kv_invoice_id;
  const goodsHandled = !!r.goods_handled_at;   // đã nhập kho / xuất hủy hàng trả
  const lockToast = () => toast("Phiếu đã có HĐ KiotViet — xoá HĐ (xoá phiếu) mới sửa được", "info");

  const startEdit = () => {
    if (invoiced) return lockToast();
    if (goodsHandled) return toast("Phiếu đã xử lý hàng (nhập/hủy) — không sửa được nữa", "info");
    if (!office) return toast("Chỉ văn phòng mới được sửa phiếu trả", "info");
    setLines((r.items || []).map((x) => ({ sp: x.sp, sl: String(x.sl), price: String(x.price) })));
    setNote(r.note || "");
    setEditing(true);
  };
  const updLine = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const parsed = lines
    .map((l) => ({ sp: l.sp.trim().toUpperCase(), sl: parseQty(l.sl), price: parseMoney(l.price) }))
    .filter((l) => l.sp && isFinite(l.sl) && l.sl > 0 && isFinite(l.price) && l.price > 0);
  const editTotal = parsed.reduce((s, l) => s + l.sl * l.price, 0);

  const saveEdit = async () => {
    if (!parsed.length) return toast("Cần ít nhất 1 dòng hàng hợp lệ", "info");
    setBusy(true);
    try {
      await updateReturn(Number(id), parsed, note.trim());
      toast("Đã lưu phiếu trả", "ok");
      setEditing(false);
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally { setBusy(false); }
  };

  const doInvoice = async () => {
    if (!office) return toast("Chỉ văn phòng mới được tạo HĐ", "info");
    if (!(await confirmDialog(`Tạo HĐ KiotViet giá âm −${soVN(r.total)}đ? Công nợ khách sẽ TRỪ ngay và phiếu bị khoá sửa.`))) return;
    setBusy(true);
    try {
      const res = await invoiceReturn(Number(id));
      toast(`Đã tạo HĐ ${res.kv_code} — nợ trừ ${soVN(r.total)}`, "ok");
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo HĐ", "err");
    } finally { setBusy(false); }
  };

  const doDeleteInvoice = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá HĐ KiotViet", "info");
    if (!(await confirmDialog("Xoá HĐ KiotViet giá âm? Công nợ khách sẽ CỘNG lại và phiếu về NHÁP (sửa/xoá được).", { danger: true }))) return;
    setBusy(true);
    try {
      await deleteReturnInvoice(Number(id));
      toast("Đã xoá HĐ KiotViet — phiếu về nháp", "ok");
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá HĐ", "err");
    } finally { setBusy(false); }
  };

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu trả", "info");
    if (invoiced) return toast("Phiếu còn HĐ KiotViet — xoá HĐ trước rồi mới xoá phiếu", "info");
    // Đã xử lý hàng → xoá phiếu KHÔNG tự hoàn tác nhập/hủy kho → cảnh báo rõ trước khi xoá.
    const msg = goodsHandled
      ? "Phiếu đã XỬ LÝ HÀNG (nhập/hủy kho). Xoá phiếu sẽ hoàn nợ cho khách nhưng KHÔNG tự hoàn tác việc đã nhập/hủy kho — hãy kiểm tra kho thủ công. Vẫn xoá?"
      : "Xoá phiếu trả nháp này?";
    if (!(await confirmDialog(msg, { danger: true }))) return;
    setBusy(true);
    try {
      await deleteReturn(Number(id));
      toast("Đã xoá phiếu trả", "ok");
      window.location.hash = "#/tra-hang";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="ret-detail">
      <PageHead fallback="#/tra-hang"
        title={<>
          <Icon name="refresh" size={18} /> Trả hàng −{soVN(r.total)}đ
          {invoiced
            ? <span class="pk-badge sx"><Icon name="receipt" size={12} /> {r.kv_invoice_code}</span>
            : <span class="pk-badge pack"><Icon name="edit" size={12} /> Nháp</span>}
        </>}
        sub={<>{fmtDateTimeVN(r.created_at)}{r.created_by ? ` · ${r.created_by}` : ""}</>} />
      {deleted && <div class="error-banner">Phiếu đã bị xoá{(r as any).deleted_by ? ` bởi ${(r as any).deleted_by}` : ""}</div>}

      <section class="card">
        <label class="card-label"><Icon name="user" size={15} /> Khách hàng</label>
        <a class="ret-cust-link" href={`#/khach/${encodeURIComponent(r.customer_key)}`}>
          {r.customer_name || r.customer_key} <Icon name="link" size={13} />
        </a>
        {invoiced && (
          <div class="muted small">
            Nợ trước: <b>{r.debt_before != null ? soVN(r.debt_before) : "—"}</b>
            {" → "}sau: <b>{r.debt_after != null ? soVN(r.debt_after) : "—"}</b>
          </div>
        )}
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Hàng trả
          {!editing && !deleted && (
            <button class={"btn small ret-edit" + (invoiced || goodsHandled || !office ? " faded" : "")} onClick={startEdit}>
              <Icon name="edit" size={13} /> Sửa
            </button>
          )}
        </label>
        {!editing ? (
          <>
            <table class="ret-items">
              <thead><tr><th>SP</th><th>SL</th><th>Giá</th><th>Tổng</th></tr></thead>
              <tbody>
                {(r.items || []).map((x, i) => (
                  <tr key={i}>
                    <td><b>{x.sp}</b></td>
                    <td>{soVN(x.sl)}</td>
                    <td>{soVN(x.price)}</td>
                    <td>{soVN(x.sl * x.price)}</td>
                  </tr>
                ))}
                <tr class="ret-sum"><td colSpan={3}>Tổng trả (trừ nợ)</td><td><b>−{soVN(r.total)}</b></td></tr>
              </tbody>
            </table>
            {r.note && <div class="ret-card-note"><Icon name="note" size={13} /> {r.note}</div>}
          </>
        ) : (
          <div class="ret-sheet">
            {lines.map((l, i) => (
              <div class="ret-line" key={i}>
                <div class="ret-sp">
                  <PickerPopup value={l.sp} placeholder="Mã SP" allowFreeText
                    onSearch={async (q): Promise<PickOpt[]> =>
                      (await searchProducts(q).catch(() => [])).map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
                    onPick={(o) => updLine(i, { sp: o.key })} />
                </div>
                <input class="ret-sl" type="text" inputMode="decimal" value={l.sl}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updLine(i, { sl: (e.target as HTMLInputElement).value })} />
                <input class="ret-price" type="text" inputMode="numeric" value={l.price}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updLine(i, { price: (e.target as HTMLInputElement).value })} />
                {lines.length > 1 && (
                  <button class="btn small" onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>
                    <Icon name="close" size={14} />
                  </button>
                )}
              </div>
            ))}
            <button class="btn small" onClick={() => setLines((prev) => [...prev, { sp: "", sl: "1", price: "" }])}>
              <Icon name="plus" size={14} /> Thêm dòng
            </button>
            <input type="text" placeholder="Ghi chú" value={note} onInput={(e) => setNote((e.target as HTMLInputElement).value)} />
            <div class="ret-total">Tổng trả: <b>−{soVN(editTotal)}đ</b></div>
            <div class="row">
              <button class="btn" onClick={() => setEditing(false)}>Huỷ</button>
              <button class="btn primary" disabled={busy || !parsed.length} onClick={saveEdit}>
                {busy ? "Đang lưu…" : "Lưu"}
              </button>
            </div>
          </div>
        )}
      </section>

      {!deleted && (() => {
        const gr = r.goods_result;
        if (r.goods_handled_at && gr) {
          const line = (arr: { sp?: string; product_code?: string; quantity: number; box_code?: string }[]) =>
            arr.map((x) => `${x.sp || x.product_code} ×${soVN(x.quantity)}${x.box_code ? ` (thùng ${x.box_code})` : ""}`).join(", ");
          return (
            <section class="card rg-summary">
              <label class="card-label"><Icon name="check" size={15} /> Hàng trả đã xử lý</label>
              <div class="muted small">{r.goods_handled_by ? `${r.goods_handled_by}` : ""}{r.goods_handled_at ? ` · ${fmtDateTimeVN(r.goods_handled_at)}` : ""}</div>
              {gr.restocked_existing?.length > 0 && <div class="rg-sum-line"><Icon name="box" size={13} /> Nhập thùng có sẵn: {line(gr.restocked_existing)}</div>}
              {gr.restocked_new?.length > 0 && <div class="rg-sum-line"><Icon name="plus" size={13} /> Thùng mới: {line(gr.restocked_new)}</div>}
              {gr.disposed?.length > 0 && (
                <div class="rg-sum-line"><Icon name="trash" size={13} /> Xuất hủy: {line(gr.disposed)}
                  {gr.disposal_id ? <> · <a href={`#/xuat-huy/${gr.disposal_id}`}>phiếu hủy #{gr.disposal_id}</a></> : null}
                </div>
              )}
            </section>
          );
        }
        return (
          <button class={"btn block rg-open-btn" + (office ? "" : " faded")} disabled={busy}
            onClick={() => office ? setShowGoods(true) : toast("Chỉ văn phòng mới được xử lý hàng trả", "info")}>
            <Icon name="box" size={15} /> Xử lý hàng trả về (nhập kho / xuất hủy)
          </button>
        );
      })()}

      {!deleted && !invoiced && (
        <button class={"btn primary block" + (office ? "" : " faded")} disabled={busy} onClick={doInvoice}>
          <Icon name="receipt" size={15} /> {busy ? "Đang tạo…" : `Tạo HĐ KiotViet (trừ nợ −${soVN(r.total)})`}
        </button>
      )}
      {invoiced && (
        <section class="card">
          <label class="card-label"><Icon name="receipt" size={15} /> Hoá đơn KiotViet (giá âm)</label>
          <div>{r.kv_invoice_code} <span class="muted small">· #{r.kv_invoice_id}</span></div>
          {!deleted && (
            <button class={"btn danger block mt-2" + (isAdmin ? "" : " faded")} disabled={busy}
              onClick={doDeleteInvoice}>
              <Icon name="trash" size={14} /> Xoá HĐ KiotViet (hoàn nợ)
            </button>
          )}
        </section>
      )}

      <Images base={`/api/media/return/${id}`} />
      <Comments base={`/api/media/return/${id}`} />
      <History base={`/api/media/return/${id}`} />

      {!deleted && (
        <button class={"btn danger block" + (isAdmin && !invoiced ? "" : " faded")} disabled={busy} onClick={doDelete}
          title={invoiced ? "Xoá HĐ KiotViet trước rồi mới xoá phiếu" : undefined}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu trả"}
        </button>
      )}

      {showGoods && (
        <ReturnGoodsModal ret={r} onClose={() => setShowGoods(false)}
          onDone={(u) => { setR(u); setShowGoods(false); }} />
      )}
    </div>
  );
}
