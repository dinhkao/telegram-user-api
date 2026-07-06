// Nhập thùng cho phiếu SX: 1 đợt = N thùng GIỐNG NHAU (cùng số cây), mã tự sinh
// (K2L-001). POST .../boxes (queueable, gửi mảng {quantity} × số thùng). onChanged()
// để phiếu tải lại tổng. Liệt kê thùng đã nhập ở phiếu này — tap → chi tiết thùng.
import { useEffect, useState } from "preact/hooks";
import { addProductionBoxes, slipBoxes, listUnits, createUnit, soVN, type ProdSlip, type InvBox, type Unit } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";

function todayLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function ProductionBoxes({
  threadId,
  slip,
  onChanged,
}: {
  threadId: string;
  slip: ProdSlip;
  onChanged: () => void;
}) {
  const hasSp = !!slip.sp_name;
  const [amount, setAmount] = useState("");
  const [count, setCount] = useState("1");
  const [note, setNote] = useState("");
  const [mfgDate, setMfgDate] = useState(todayLocal());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [myBoxes, setMyBoxes] = useState<InvBox[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState<number | null>(null);   // đơn vị chứa cho đợt nhập
  const [newUnit, setNewUnit] = useState<string | null>(null);
  useEffect(() => { listUnits().then((u) => { setUnits(u); if (u[0] && unitId == null) setUnitId(u[0].id); }).catch(() => {}); }, []);
  const pickUnit = async (val: string) => {
    if (val === "__new") { setNewUnit(""); return; }
    setUnitId(val ? Number(val) : null);
  };
  const saveNewUnit = async () => {
    const name = (newUnit || "").trim();
    if (!name) { setNewUnit(null); return; }
    try {
      const u = await createUnit(name);
      setUnits((prev) => (prev.some((x) => x.id === u.id) ? prev : [...prev, u]));
      setUnitId(u.id);
    } catch { /* im */ }
    setNewUnit(null);
  };

  const loadMine = async () => {
    try {
      setMyBoxes(await slipBoxes(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    loadMine();
  }, [slip.sp_name, slip.total]);
  // Realtime: thùng đổi ở nơi khác (sửa ghi chú/số cây/vô hiệu/xuất) không luôn đổi
  // slip.total → tự tải lại list thùng của phiếu này.
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "box_changed" || e.type === "inventory_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(loadMine, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  const submit = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n) || n <= 0) {
      setMsg("Số cây không hợp lệ");
      return;
    }
    const c = Math.floor(parseFloat(count.replace(",", ".")));
    if (!isFinite(c) || c <= 0) {
      setMsg("Số thùng không hợp lệ");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const picks = Array.from({ length: c }, () => ({ quantity: n }));  // c thùng giống nhau
      const r = await addProductionBoxes(threadId, picks, note.trim(), mfgDate, unitId);
      setAmount("");
      setCount("1");
      setNote("");
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      } else {
        setMsg(`✅ Đã nhập ${c} thùng`);
        onChanged();
        loadMine();
      }
    } catch (e: any) {
      setMsg(e?.message || "Lỗi nhập thùng");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label"><Icon name="box" size={16} /> Nhập thùng {slip.sp_name ? `(${slip.sp_name})` : ""}</label>
      {!hasSp && <div class="muted small">Chọn sản phẩm trước khi nhập.</div>}

      <div class="row">
        <label class="inline-label"><Icon name="calendar" size={16} /> NSX</label>
        <input
          type="date"
          value={mfgDate}
          disabled={!hasSp}
          onInput={(e) => setMfgDate((e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="row">
        <label class="inline-label"><Icon name="box" size={16} /> Đơn vị</label>
        {newUnit === null ? (
          <select class="box-place" value={unitId ?? ""} disabled={!hasSp} onChange={(e: any) => pickUnit(e.target.value)}>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            <option value="__new">➕ Đơn vị mới…</option>
          </select>
        ) : (
          <span class="row" style={{ gap: "6px" }}>
            <input class="box-place" autofocus placeholder="Tên đơn vị (vd Bọc, Kiện)" value={newUnit}
              onInput={(e: any) => setNewUnit(e.target.value)}
              onKeyDown={(e: any) => { if (e.key === "Enter") saveNewUnit(); if (e.key === "Escape") setNewUnit(null); }} />
            <button class="btn small primary" onClick={saveNewUnit}>Lưu</button>
            <button class="btn small" onClick={() => setNewUnit(null)}>✕</button>
          </span>
        )}
      </div>
      <div class="row">
        <input
          type="text"
          inputMode="numeric"
          class="pb-count"
          value={count}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setCount((e.target as HTMLInputElement).value)}
          placeholder="Số thùng"
          title="Số thùng giống nhau"
        />
        <span class="pb-x">thùng ×</span>
        <input
          type="text"
          inputMode="decimal"
          class="pb-amount"
          value={amount}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
          placeholder="Số cây / thùng"
        />
      </div>
      <div class="row">
        <input
          type="text"
          value={note}
          disabled={!hasSp}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)}
          placeholder="Ghi chú (tuỳ chọn)"
        />
        <button class="btn primary" disabled={!hasSp || busy} onClick={submit}>
          {busy ? "…" : <Icon name="plus" size={16} />}
        </button>
      </div>
      {msg && <div class="muted small">{msg}</div>}

      {myBoxes.length > 0 && (
        <div class="inv-summary">
          <div class="inv-total">Thùng nhập ở phiếu này ({myBoxes.length})</div>
          {/* Trực quan: mỗi thùng = 1 ô vuông, màu theo trạng thái; tap → chi tiết thùng */}
          <div class="box-grid">
            {myBoxes.map((b) => {
              const rem = b.remaining ?? b.quantity;
              const used = b.allocated ?? 0;
              const st = b.disabled ? "off" : used > 0 ? "alloc" : "in";
              const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
              return (
                <a
                  key={b.id}
                  id={`box-${b.id}`}
                  class={`box-sq ${st}`}
                  href={`#/thung/${b.id}`}
                  title={`${b.box_code} · ${soVN(rem)} cây · ${status}${b.note ? ` · ${b.note}` : ""}`}
                >
                  {b.note && <span class="bs-dot" />}
                  <span class="bs-q">{soVN(rem)}</span>
                  <span class="bs-code">{b.box_code}</span>
                </a>
              );
            })}
          </div>
          <div class="box-legend">
            <span><i class="bl in" />Trong kho</span>
            <span><i class="bl alloc" />Đã xuất</span>
            <span><i class="bl off" />Vô hiệu</span>
          </div>
        </div>
      )}
    </section>
  );
}
