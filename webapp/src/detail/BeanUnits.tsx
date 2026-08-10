// QUY ĐỔI ĐƠN VỊ của 1 loại đậu — khối bung ra trong #/kho-dau/thiet-lap.
// 1 <tên> = <tỉ lệ> đơn vị GỐC (vd 1 bao = 50 kg). Thêm = mọi user, sửa tỉ lệ =
// văn phòng, xoá = admin. Nối: api.addBeanUnit/updateBeanUnit/deleteBeanUnit.
import { useState } from "preact/hooks";
import {
  addBeanUnit, currentUser, deleteBeanUnit, isOffice, soVN, updateBeanUnit,
  type Bean, type BeanUnit,
} from "../api";
import { parseQty } from "../format";
import { Icon } from "../ui/Icon";
import { confirmDialog, promptDialog, toast } from "../ui/feedback";

export function BeanUnits({ bean, onChanged }: { bean: Bean; onChanged: () => Promise<any> | void }) {
  const [name, setName] = useState("");
  const [factor, setFactor] = useState("");
  const [busy, setBusy] = useState(false);
  const office = isOffice();
  const admin = currentUser()?.role === "admin";
  const units: BeanUnit[] = bean.units || [];

  const run = async (fn: () => Promise<any>, okMsg: string) => {
    setBusy(true);
    try { await fn(); await onChanged(); toast(okMsg, "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  const add = () => {
    const n = name.trim();
    const f = parseQty(factor);
    if (!n) return toast("Nhập tên đơn vị (vd bao)", "info");
    if (!(f > 0)) return toast(`Nhập 1 ${n || "đơn vị"} bằng bao nhiêu ${bean.unit}`, "info");
    run(async () => { await addBeanUnit(bean.id, n, f); setName(""); setFactor(""); },
        "Đã thêm đơn vị");
  };

  const editFactor = async (u: BeanUnit) => {
    const v = await promptDialog(`1 ${u.name} bằng bao nhiêu ${bean.unit}?`,
      { initial: String(u.factor), okLabel: "Lưu" });
    if (v === null) return;
    const f = parseQty(v);
    if (!(f > 0)) return toast("Tỉ lệ phải lớn hơn 0", "err");
    run(() => updateBeanUnit(bean.id, u.id, { factor: f }), "Đã đổi tỉ lệ");
  };
  const rename = async (u: BeanUnit) => {
    const v = await promptDialog("Tên đơn vị", { initial: u.name, okLabel: "Lưu" });
    if (v === null || !v.trim() || v.trim() === u.name) return;
    run(() => updateBeanUnit(bean.id, u.id, { name: v.trim() }), "Đã đổi tên đơn vị");
  };
  const del = async (u: BeanUnit) => {
    if (!(await confirmDialog(`Xoá đơn vị "${u.name}" của ${bean.name}?`,
      { danger: true, okLabel: "Xoá đơn vị" }))) return;
    run(() => deleteBeanUnit(bean.id, u.id), "Đã xoá đơn vị");
  };

  return (
    <div class="bean-units">
      <div class="bean-units-base muted small">
        Đơn vị gốc: <b>{bean.unit}</b> — mọi số tồn kho tính theo đơn vị này.
      </div>
      {units.map((u) => (
        <div class="bean-unit-row" key={u.id}>
          <div class="bean-unit-txt">
            1 <b>{u.name}</b> = {soVN(u.factor)} {bean.unit}
          </div>
          {office && (
            <>
              <button class="btn small" title="Đổi tên" disabled={busy} onClick={() => rename(u)}>
                <Icon name="edit" size={13} />
              </button>
              <button class="btn small" title="Đổi tỉ lệ" disabled={busy} onClick={() => editFactor(u)}>
                <Icon name="refresh" size={13} />
              </button>
            </>
          )}
          {admin && (
            <button class="btn small danger" title="Xoá" disabled={busy} onClick={() => del(u)}>
              <Icon name="trash" size={13} />
            </button>
          )}
        </div>
      ))}
      <div class="bean-unit-add">
        <input class="bean-in" placeholder="Tên (vd bao)" value={name}
          onInput={(e: any) => setName(e.target.value)} />
        <span class="muted small">=</span>
        <input class="bean-in bean-unit-in" type="text" inputMode="decimal"
          placeholder={bean.unit} value={factor}
          onInput={(e: any) => setFactor(e.target.value)}
          onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
        <button class="btn primary" disabled={busy || !name.trim() || !factor.trim()} onClick={add}>
          <Icon name="plus" size={15} />
        </button>
      </div>
      {office && units.length > 0 && (
        <p class="muted small">
          Đổi tỉ lệ chỉ áp cho phiếu tạo SAU đó — phiếu cũ giữ nguyên số đã quy đổi lúc nhập.
        </p>
      )}
    </div>
  );
}
