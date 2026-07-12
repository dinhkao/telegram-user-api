// Popup chọn thùng để xuất cho đơn — liệt kê thùng khả dụng (in_stock, còn hiệu
// lực) kèm info (số cây, NSX, ghi chú). Chọn nhiều thùng, mỗi thùng có thể lấy 1
// phần (mặc định full thùng). Trả picks cho OrderStock gọi allocatePicks.
import { useEffect, useMemo, useState } from "preact/hooks";
import { inventoryDetail, soVN, type InvBox } from "../api";
import { onRealtime } from "../realtime";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { LoadingInline } from "../ui/states";

function fmtDate(s?: string | null): string {
  if (!s) return "";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : s;   // NSX gọn: DD/MM
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
  // Sắp: còn hàng trước → NSX CŨ NHẤT trước (FEFO) → CÒN ÍT NHẤT trước (dọn thùng lẻ) → mã
  const mfgKey = (b: InvBox) => b.mfg_date || "9999-99-99";
  const sortPick = (a: InvBox, b: InvBox) =>
    (avail(b) > 0 ? 1 : 0) - (avail(a) > 0 ? 1 : 0)
    || mfgKey(a).localeCompare(mfgKey(b))
    || avail(a) - avail(b)
    || (a.box_code || "").localeCompare(b.box_code || "");
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
          <span class={"sp-total" + (full && remaining > 0 ? " ok" : "")}>
            <b>{soVN(pickedSum)}</b><span class="sp-total-sep">/</span>{soVN(remaining)}
          </span>
          <button class="link-btn" onClick={onClose}>
            <Icon name="close" size={18} />
          </button>
        </div>
        <div class="muted small">
          Cần {soVN(need)} · đã xuất {soVN(got)} · còn thiếu {soVN(remaining)}
        </div>

        {!boxes ? (
          <div class="muted"><LoadingInline /></div>
        ) : boxes.length === 0 ? (
          <div class="muted small">Kho hết thùng {productCode}.</div>
        ) : (
          <div class="sp-list">
            {boxes.slice().sort(sortPick).map((b) => {
              const checked = b.id in sel;
              const blocked = !checked && full;   // hết ngân sách → không cho chọn thêm
              const num = (b.box_code || "").split("-").pop() || b.box_code;
              const unit = (b as any).product_unit || "cây";
              const after = Math.max(0, avail(b) - parseN(sel[b.id] || ""));   // còn lại SAU khi lấy
              const place = (b as any).place_name as string | undefined;
              const nsx = b.mfg_date ? fmtDate(b.mfg_date) : "";
              return (
                <div class={"sp-row" + (checked ? " on" : "") + (blocked ? " off" : "")} key={b.id}>
                  <div class="sp-tap" onClick={() => { if (!blocked) toggle(b); }} title={b.box_code}>
                    <div class="sp-main">
                      <span class="sp-check">{checked ? <Icon name="check" size={13} /> : <span class="sp-dot" />}</span>
                      <span class="sp-code">{num}</span>
                      <span class="sp-qty">{soVN(avail(b))}
                        {checked
                          ? <span class={"sp-after" + (after <= 0 ? " done" : "")}>→ {after <= 0 ? "hết" : soVN(after)}</span>
                          : <i>{unit}</i>}
                      </span>
                      {/* chọn → CSS xếp vị trí & NSX thành 2 dòng để không bị cắt */}
                      <span class="sp-meta">
                        {place ? <span>📍 {place}</span> : null}
                        {nsx ? <span>NSX {nsx}</span> : null}
                      </span>
                    </div>
                    {b.note ? <div class="sp-notel" title={b.note}>📝 {b.note}</div> : null}
                  </div>
                  {checked && (
                    <label class="sp-takewrap" title="Số lấy từ thùng này">
                      <span class="sp-takel">lấy</span>
                      <input class="sp-take" type="text" inputMode="decimal" value={sel[b.id]}
                        onFocus={(e) => (e.target as HTMLInputElement).select()}
                        onInput={(e) => setQty(b.id, (e.target as HTMLInputElement).value)} />
                    </label>
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
