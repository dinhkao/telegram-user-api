// Khối TIỀN CÔNG + PHỤ CẤP của 1 phiếu SX — CHỈ văn phòng (parent gate isOffice()).
// Đơn giá lương /1SP CHỐT THEO PHIẾU (sửa ở đây chỉ ảnh hưởng phiếu này; mặc định
// chốt từ bảng lương lúc gán SP). Mỗi thợ: tiền SP (số cây × đơn giá) + ô nhập
// PHỤ CẤP (lưu ngay khi rời ô) = tổng. Data: phieuWages() (đơn giá + phụ cấp),
// setPhieuWage(), setAllowance(). Server chặn 403 nếu không office.
import { useEffect, useState } from "preact/hooks";
import { phieuWages, setAllowance, setPhieuWage, soVN } from "../api";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";

const money = (n: number) => soVN(Math.round(n)) + "đ";

export function ProductionWages({ threadId, workers }: { threadId: string; workers: { name: string; cay: number }[] }) {
  const [wage, setWage] = useState(0);
  const [defaultWage, setDefaultWage] = useState(0);
  const [wageDraft, setWageDraft] = useState<string | null>(null);
  const [allow, setAllow] = useState<Record<string, number>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let ok = true;
    phieuWages(threadId).then((d) => { if (ok) { setWage(d.wage); setDefaultWage(d.default_wage); setAllow(d.allowances || {}); setLoaded(true); } }).catch(() => { if (ok) setLoaded(true); });
    return () => { ok = false; };
  }, [threadId]);

  const saveWage = async () => {
    if (wageDraft === null) return;
    const luong = Number(wageDraft.replace(/[^\d.]/g, "") || 0);
    setWageDraft(null);
    if (luong === wage) return;
    try {
      await setPhieuWage(threadId, luong);
      setWage(luong);
      toast(`Đã chốt đơn giá phiếu này: ${money(luong)}/SP`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu đơn giá", "err"); }
  };

  const save = async (name: string) => {
    const raw = draft[name];
    if (raw === undefined) return;                       // chưa gõ gì
    const amount = raw.trim() === "" ? 0 : Number(raw.replace(/[^\d]/g, ""));
    if (isNaN(amount)) { toast("Số tiền không hợp lệ", "err"); return; }
    if (amount === (allow[name] || 0)) { setDraft((d) => { const n = { ...d }; delete n[name]; return n; }); return; }
    try {
      await setAllowance(threadId, name, amount);
      setAllow((a) => ({ ...a, [name]: Math.max(0, amount) }));
      setDraft((d) => { const n = { ...d }; delete n[name]; return n; });
      toast("Đã lưu phụ cấp", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu phụ cấp", "err"); }
  };

  if (!loaded) return null;
  const list = workers.filter((w) => w.name);
  if (!list.length) return null;

  let totPiece = 0, totAllow = 0;
  const rows = list.map((w) => {
    const piece = Math.round(w.cay * wage);
    const a = allow[w.name] || 0;
    totPiece += piece; totAllow += a;
    return { name: w.name, cay: w.cay, piece, a };
  });

  return (
    <div class="pw-box">
      <div class="pw-head"><Icon name="wallet" size={15} /> Tiền công + phụ cấp (văn phòng)</div>
      <div class="pw-wage-row">
        <span class="pw-wage-lbl">Đơn giá phiếu này:</span>
        <input class="pw-input pw-wage-input" inputMode="numeric"
          value={wageDraft !== null ? wageDraft : (wage ? String(wage) : "")}
          placeholder="0"
          onInput={(e: any) => setWageDraft(e.target.value)}
          onBlur={saveWage}
          onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
        <span class="muted small">đ/SP</span>
        {defaultWage !== wage ? <span class="pw-wage-note muted small">bảng lương: {soVN(defaultWage)}đ</span> : null}
      </div>
      <div class="pw-scroll">
        <table class="pw-table">
          <thead><tr><th>Thợ</th><th>Tiền SP</th><th>Phụ cấp</th><th>Tổng</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td class="pw-name">{r.name}</td>
                <td class="pw-piece">{money(r.piece)}<span class="muted pw-sub"> {soVN(r.cay)}×{soVN(wage)}</span></td>
                <td class="pw-allow">
                  <input class="pw-input" inputMode="numeric" placeholder="0"
                    value={draft[r.name] !== undefined ? draft[r.name] : (r.a ? String(r.a) : "")}
                    onInput={(e: any) => setDraft((d) => ({ ...d, [r.name]: e.target.value }))}
                    onBlur={() => save(r.name)}
                    onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                </td>
                <td class="pw-total">{money(r.piece + r.a)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr><td>TỔNG</td><td>{money(totPiece)}</td><td>{money(totAllow)}</td><td class="pw-total">{money(totPiece + totAllow)}</td></tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
