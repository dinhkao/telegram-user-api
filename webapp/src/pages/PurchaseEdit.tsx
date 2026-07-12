// Trang SỬA phiếu nhập hàng (#/nhap-hang/:id/sua) — tách khỏi trang chi tiết,
// tương tự trang sửa hoá đơn của đơn. Lưu xong quay về chi tiết phiếu.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getPurchase, isOffice, searchProducts, soVN,
  updatePurchase, type PurchaseSlip,
} from "../api";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { toast } from "../ui/feedback";
import { ErrorState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string };

export function PurchaseEdit({ id }: { id: string }) {
  const [purchase, setPurchase] = useState<PurchaseSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [note, setNote] = useState("");
  const office = isOffice();

  const load = async () => {
    try {
      const r = await getPurchase(id);
      setPurchase(r);
      setLines((r.items || []).map((x) => ({ sp: x.sp, sl: String(x.sl), price: String(x.price) })));
      setNote(r.note || "");
      setErr("");
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải phiếu");
    }
  };

  useEffect(() => { load(); }, [id]);

  const updateLine = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((line, j) => (j === i ? { ...line, ...patch } : line)));

  const parsed = lines
    .map((line) => ({
      sp: line.sp.trim().toUpperCase(),
      sl: parseFloat(line.sl.replace(",", ".")),
      price: parseFloat(line.price.replace(/\./g, "").replace(",", ".")),
    }))
    .filter((line) => line.sp && isFinite(line.sl) && line.sl > 0 && isFinite(line.price) && line.price >= 0);
  const total = parsed.reduce((sum, line) => sum + line.sl * line.price, 0);
  const deleted = !!purchase?.deleted_at;

  const save = async () => {
    if (!office) return toast("Chỉ văn phòng mới được sửa phiếu nhập", "info");
    if (deleted) return toast("Phiếu đã bị xoá, không thể sửa", "info");
    if (!parsed.length) return toast("Cần ít nhất 1 dòng hàng hợp lệ", "info");
    setBusy(true);
    try {
      await updatePurchase(Number(id), parsed, note.trim());
      toast("Đã lưu phiếu nhập", "ok");
      window.location.hash = `#/nhap-hang/${id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu phiếu", "err");
    } finally {
      setBusy(false);
    }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!purchase) return <Loading />;

  return (
    <div class="pur-edit-page">
      <div class="prod-detail-head">
        <BackLink fallback={`#/nhap-hang/${id}`} />
        <div>
          <div class="prod-sp big"><Icon name="edit" size={18} /> Sửa phiếu nhập</div>
          <div class="prod-date muted">
            {purchase.supplier_name || `NCC #${purchase.supplier_id}`} · Phiếu #{purchase.id}
          </div>
        </div>
      </div>

      {!office && (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> Chỉ văn phòng mới được sửa phiếu nhập.
        </div>
      )}
      {deleted && (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> Phiếu đã bị xoá{purchase.deleted_by ? ` bởi ${purchase.deleted_by}` : ""} — không thể sửa.
        </div>
      )}

      {office && !deleted && (
        <section class="card pur-edit-card">
          <div class="card-label"><Icon name="box" size={15} /> Hàng nhập</div>
          <div class="ret-sheet">
            {lines.map((line, i) => (
              <div class="ret-line" key={i}>
                <div class="ret-sp">
                  <PickerPopup
                    value={line.sp}
                    placeholder="Mã SP"
                    allowFreeText
                    onSearch={async (q): Promise<PickOpt[]> =>
                      (await searchProducts(q).catch(() => []))
                        .filter((s) => s.can_purchase !== false)
                        .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
                    onPick={(option) => updateLine(i, { sp: option.key })}
                  />
                </div>
                <input
                  class="ret-sl"
                  type="text"
                  inputMode="decimal"
                  value={line.sl}
                  aria-label={`Số lượng dòng ${i + 1}`}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updateLine(i, { sl: (e.target as HTMLInputElement).value })}
                />
                <input
                  class="ret-price"
                  type="text"
                  inputMode="numeric"
                  value={line.price}
                  aria-label={`Đơn giá dòng ${i + 1}`}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updateLine(i, { price: (e.target as HTMLInputElement).value })}
                />
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
            <input
              type="text"
              placeholder="Ghi chú"
              value={note}
              onInput={(e) => setNote((e.target as HTMLInputElement).value)}
            />
            <div class="ret-total">Tổng nhập: <b>{soVN(total)}đ</b></div>
            <div class="row pur-edit-actions">
              <a class="btn" href={`#/nhap-hang/${id}`}>Huỷ</a>
              <button class="btn primary" disabled={busy || !parsed.length} onClick={save}>
                {busy ? "Đang lưu…" : "Lưu phiếu"}
              </button>
            </div>
          </div>
        </section>
      )}

    </div>
  );
}
