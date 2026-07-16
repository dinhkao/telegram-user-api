// Khối ĐIỀU CHỈNH TỒN của 1 thùng (chi tiết thùng #/thung/:id) — văn phòng nhập
// TỒN THỰC TẾ + lý do bắt buộc → tạo phiếu điều chỉnh (allocation kind='adjustment',
// không sửa quantity gốc). Danh sách phiếu của thùng hiện dưới; admin gỡ = hoàn
// nguyên (server chặn nếu gây tồn âm). Data: adjustBox/listAdjustments/deleteAdjustment.
import { useEffect, useState } from "preact/hooks";
import { adjustBox, listAdjustments, deleteAdjustment, currentUser, isOffice, soVN, type Adjustment } from "../api";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";

export function BoxAdjust({ boxId, remaining, unit, onChanged }: {
  boxId: number; remaining: number; unit: string; onChanged: () => void;
}) {
  const office = isOffice();
  const isAdmin = currentUser()?.role === "admin";
  const [list, setList] = useState<Adjustment[]>([]);
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => listAdjustments({ box_id: boxId }).then(setList).catch(() => {});
  useEffect(() => { load(); }, [boxId]);

  const q = parseFloat((qty || "").replace(",", "."));
  const ok = isFinite(q) && q >= 0 && Math.abs(q - remaining) > 1e-9 && !!reason.trim();

  const submit = async () => {
    if (!ok) { toast("Nhập tồn thực tế (khác số hệ thống) + lý do", "info"); return; }
    const delta = q - remaining;
    if (!(await confirmDialog(
      `Điều chỉnh tồn thùng: ${soVN(remaining)} → ${soVN(q)} ${unit} (${delta > 0 ? "+" : ""}${soVN(delta)})?\nLý do: ${reason.trim()}`)))
      return;
    setBusy(true);
    try {
      await adjustBox(boxId, q, reason.trim());
      toast("Đã tạo phiếu điều chỉnh", "ok");
      setQty(""); setReason("");
      load(); onChanged();
    } catch (e: any) {
      toast(e?.message || "Lỗi điều chỉnh", "err");
    } finally { setBusy(false); }
  };
  const del = async (a: Adjustment) => {
    if (!(await confirmDialog(`Gỡ phiếu điều chỉnh ${a.delta > 0 ? "+" : ""}${soVN(a.delta)} (hoàn nguyên tồn)?`, { danger: true }))) return;
    try { await deleteAdjustment(a.id); toast("Đã gỡ phiếu — tồn hoàn nguyên", "ok"); load(); onChanged(); }
    catch (e: any) { toast(e?.message || "Lỗi gỡ phiếu", "err"); }
  };

  const alive = list.filter((a) => !a.deleted_at);
  if (!office && !alive.length) return null;

  return (
    <section class="card">
      <label class="card-label"><Icon name="edit" size={15} /> Điều chỉnh tồn (phiếu điều chỉnh)</label>
      {office && (
        <>
          <div class="row" style={{ gap: "6px" }}>
            <input class="pb-amount" style={{ width: "84px" }} type="text" inputMode="decimal"
              placeholder={`${soVN(remaining)}`} value={qty}
              onFocus={(e: any) => (e.target as HTMLInputElement).select()}
              onInput={(e: any) => setQty(e.target.value)} />
            <input style={{ flex: 1, minWidth: 0 }} type="text" placeholder="Lý do điều chỉnh (bắt buộc)"
              value={reason} onInput={(e: any) => setReason(e.target.value)} />
            <button class={"btn primary" + (ok ? "" : " faded")} disabled={busy} onClick={submit}
              title={ok ? undefined : "Nhập tồn thực tế + lý do"}>Lưu</button>
          </div>
          <div class="muted small" style={{ marginTop: "4px" }}>
            Nhập <b>tồn thực tế</b> — hệ thống đang ghi {soVN(remaining)} {unit}. Không sửa số gốc của thùng;
            mọi điều chỉnh có phiếu + lịch sử, admin gỡ được (hoàn nguyên).
          </div>
        </>
      )}
      {list.length > 0 && (
        <ul class="box-alloc-list" style={{ marginTop: "6px" }}>
          {list.map((a) => (
            <li key={a.id} class={a.deleted_at ? "adj-deleted" : ""}>
              <span class="box-jump adj-row">
                <Icon name="edit" size={15} />{" "}
                <span style={a.deleted_at ? { textDecoration: "line-through", opacity: 0.6 } : undefined}>
                  {a.delta > 0 ? "+" : ""}{soVN(a.delta)} {unit}
                  {a.old_remaining != null && a.new_remaining != null ? ` (${soVN(a.old_remaining)} → ${soVN(a.new_remaining)})` : ""}
                  {a.source === "stocktake" && a.stocktake_id ? <> · <a href={`#/kiem-kho/${a.stocktake_id}`}>kiểm kho #{a.stocktake_id}</a></> : null}
                  {" · "}{a.reason}
                  {a.created_by ? ` · ${a.created_by}` : ""}
                  {a.deleted_at ? ` · đã gỡ${a.deleted_by ? ` bởi ${a.deleted_by}` : ""}` : ""}
                </span>
                {isAdmin && !a.deleted_at && (
                  <button class="icon-btn adj-del" title="Gỡ phiếu (hoàn nguyên)" onClick={() => del(a)}>
                    <Icon name="close" size={14} />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
