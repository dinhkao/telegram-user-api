// Popup chọn thùng để xuất cho đơn — liệt kê thùng khả dụng (in_stock, còn hiệu
// lực) kèm info (số cây, NSX, ghi chú). Chọn nhiều thùng, mỗi thùng có thể lấy 1
// phần (mặc định full thùng). Trả picks cho OrderStock gọi allocatePicks.
import { useEffect, useMemo, useState } from "preact/hooks";
import { inventoryDetail, soVN, type InvBox } from "../api";
import { onRealtime } from "../realtime";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";

function fmtDate(s?: string | null): string {
  if (!s) return "";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
}

export function StockPickerModal({
  productCode,
  need,
  got,
  onClose,
  onPick,
  initial,
}: {
  productCode: string;
  need: number;
  got: number;
  onClose: () => void;
  onPick: (picks: { box_id: number; quantity: number }[]) => Promise<void>;
  initial?: { box_id: number; quantity: number }[];   // seed sẵn (sửa lại lựa chọn cũ)
}) {
  useScrollLock(true);
  usePopupBack(true, onClose);
  const [boxes, setBoxes] = useState<InvBox[] | null>(null);
  const [sel, setSel] = useState<Record<number, string>>(
    () => Object.fromEntries((initial || []).map((p) => [p.box_id, String(p.quantity)]))
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () =>
    inventoryDetail(productCode)
      .then((d) => setBoxes(d.boxes))
      .catch((e: any) => setErr(e?.message || "Lỗi tải kho"));
  useEffect(() => { load(); }, [productCode]);
  // Realtime: kho/thùng đổi (nơi khác xuất/nhập/vô hiệu) → cập nhật list thùng khả dụng
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "box_changed" || e.type === "inventory_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [productCode]);

  const remaining = Math.max(need - got, 0);   // NGÂN SÁCH: không được chọn quá số này

  const avail = (b: InvBox) => (b.remaining != null ? b.remaining : b.quantity);
  const parseN = (v: any) => { const n = parseFloat(String(v).replace(",", ".")); return isFinite(n) && n > 0 ? n : 0; };
  // tổng đã chọn ở các thùng KHÁC id → phần ngân sách còn lại cho thùng này
  const sumExcept = (id: number) => Object.entries(sel).reduce((t, [k, v]) => t + (Number(k) === id ? 0 : parseN(v)), 0);
  // trần lấy từ 1 thùng = min(còn trong thùng, ngân sách còn lại)
  const maxFor = (b: InvBox) => Math.max(0, Math.min(avail(b), remaining - sumExcept(b.id)));

  const toggle = (b: InvBox) =>
    setSel((s) => {
      const n = { ...s };
      if (b.id in n) { delete n[b.id]; return n; }
      const others = Object.entries(s).reduce((t, [k, v]) => t + (Number(k) === b.id ? 0 : parseN(v)), 0);
      const cap = Math.max(0, Math.min(avail(b), remaining - others));   // chỉ điền phần còn thiếu
      if (cap <= 0) return n;   // hết ngân sách → không thêm
      n[b.id] = String(cap);
      return n;
    });
  const setQty = (id: number, v: string) =>
    setSel((s) => {
      const b = boxes?.find((x) => x.id === id);
      const others = Object.entries(s).reduce((t, [k, vv]) => t + (Number(k) === id ? 0 : parseN(vv)), 0);
      const cap = b ? Math.max(0, Math.min(avail(b), remaining - others)) : remaining - others;
      const n = parseN(v);
      // kẹp: không cho vượt trần; giữ chuỗi rỗng khi đang gõ
      return { ...s, [id]: v === "" ? "" : n > cap ? String(cap) : v };
    });

  const pickedSum = useMemo(() => Object.values(sel).reduce((t, v) => t + parseN(v), 0), [sel]);
  const full = pickedSum + 1e-6 >= remaining;   // đã chọn đủ ngân sách

  const submit = async () => {
    const picks: { box_id: number; quantity: number }[] = [];
    for (const [id, v] of Object.entries(sel)) {
      const n = parseFloat(String(v).replace(",", "."));
      if (isFinite(n) && n > 0) picks.push({ box_id: Number(id), quantity: n });
    }
    if (!picks.length) {
      setErr("Chưa chọn thùng");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await onPick(picks);
      onClose();
    } catch (e: any) {
      setErr(e?.message || "Lỗi xuất kho");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={onClose}>
      <div class="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div class="modal-head">
          <b>Chọn thùng — {productCode}</b>
          <button class="link-btn" onClick={onClose}>
            <Icon name="close" size={18} />
          </button>
        </div>
        <div class="muted small">
          Cần {soVN(need)} · đã xuất {soVN(got)} · còn thiếu {soVN(remaining)}
        </div>

        {!boxes ? (
          <div class="muted">Đang tải…</div>
        ) : boxes.length === 0 ? (
          <div class="muted small">Kho hết thùng {productCode}.</div>
        ) : (
          <div class="stock-pick-list">
            {boxes.slice().sort((a, b) => (avail(b) > 0 ? 1 : 0) - (avail(a) > 0 ? 1 : 0)).map((b) => {
              const checked = b.id in sel;
              const blocked = !checked && full;   // hết ngân sách → không cho chọn thêm
              return (
                <div class={checked ? "stock-pick-row on" : blocked ? "stock-pick-row off" : "stock-pick-row"} key={b.id}>
                  <label class="stock-pick-main">
                    <input type="checkbox" checked={checked} disabled={blocked} onChange={() => toggle(b)} />
                    <span class="stock-pick-info">
                      <code>{b.box_code}</code>
                      <span class="muted small">
                        còn {soVN(avail(b))}
                        {b.remaining != null && b.remaining !== b.quantity ? `/${soVN(b.quantity)}` : ""} {(b as any).product_unit || "cây"}
                        {b.mfg_date ? ` · NSX ${fmtDate(b.mfg_date)}` : ""}
                        {b.note ? ` · 📝 ${b.note}` : ""}
                      </span>
                    </span>
                  </label>
                  {checked && (
                    <input
                      class="stock-pick-qty"
                      type="text"
                      inputMode="decimal"
                      value={sel[b.id]}
                      onFocus={(e) => (e.target as HTMLInputElement).select()}
                      onInput={(e) => setQty(b.id, (e.target as HTMLInputElement).value)}
                      title="Số cây lấy từ thùng này"
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {err && <div class="error-banner">{err}</div>}
        <div class="modal-foot">
          <span class={full && remaining > 0 ? "inv-pick-sum ok" : "inv-pick-sum"}>
            Chọn {soVN(pickedSum)}/{soVN(remaining)}
          </span>
          <button class="btn primary" disabled={busy || !pickedSum} onClick={submit}>
            {busy ? "…" : "Xong"}
          </button>
        </div>
      </div>
    </div>
  );
}
