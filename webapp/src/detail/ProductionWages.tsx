// Khối TIỀN CÔNG + PHỤ CẤP của 1 phiếu SX — CHỈ văn phòng (parent gate isOffice()).
// Đơn giá lương /1SP CHỐT THEO PHIẾU (sửa ở đây chỉ ảnh hưởng phiếu này; mặc định
// chốt từ bảng lương lúc gán SP). Mỗi thợ: tiền SP (số cây × đơn giá) + ô PHỤ CẤP:
// bấm ô → popup chọn nhanh (bằng tiền SP cao nhất/nhì/ba của bảng — KHÔNG tính phụ
// cấp, bằng 1 thợ cụ thể, hoặc Tự nhập → ô mở khoá gõ tay, lưu khi rời ô).
// Data: phieuWages() (đơn giá + phụ cấp), setPhieuWage(), setAllowance().
// Server chặn 403 nếu không office.
import { useEffect, useRef, useState } from "preact/hooks";
import { phieuWages, setAllowance, setPhieuWage, soVN } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { SelectPopup } from "../ui/SelectPopup";

const money = (n: number) => soVN(Math.round(n)) + "đ";

export function ProductionWages({ threadId, workers }: { threadId: string; workers: { name: string; cay: number; gio?: number; note?: string }[] }) {
  const [wage, setWage] = useState(0);
  const [defaultWage, setDefaultWage] = useState(0);
  const [wageDraft, setWageDraft] = useState<string | null>(null);
  const [allow, setAllow] = useState<Record<string, number>>({});
  const [hourly, setHourly] = useState<Record<string, number>>({});   // tiền 1 GIỜ theo thợ
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [allowPop, setAllowPop] = useState<string | null>(null); // popup phụ cấp: tên thợ đang chọn
  const [manual, setManual] = useState<string | null>(null);     // thợ đang "Tự nhập" (ô mở khoá gõ tay)
  const allowInputs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    let ok = true;
    const load = () =>
      phieuWages(threadId).then((d) => { if (ok) { setWage(d.wage); setDefaultWage(d.default_wage); setAllow(d.allowances || {}); setHourly(d.hourly_rates || {}); setLoaded(true); } }).catch(() => { if (ok) setLoaded(true); });
    load();
    // đổi tiền 1 giờ / bảng lương từ máy khác → tải lại đơn giá (khỏi kẹt số cũ).
    // production_changed của CHÍNH phiếu: lưu báo cáo có thể vừa áp PHỤ CẤP TỰ ĐỘNG
    // theo ghi chú (allowance_auto) → tải lại để hiện số mới.
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "workers_changed" || e.type === "productions_changed"
        || (e.type === "production_changed" && String((e as any).thread_id || "") === String(threadId))) {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { ok = false; off(); clearTimeout(t); };
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

  // Lưu phụ cấp = 1 SỐ CỤ THỂ (chọn từ popup) — không qua draft
  const applyAllow = async (name: string, amount: number) => {
    setDraft((d) => { const n = { ...d }; delete n[name]; return n; });
    if (amount === (allow[name] || 0)) return;
    try {
      await setAllowance(threadId, name, amount);
      setAllow((a) => ({ ...a, [name]: Math.max(0, amount) }));
      toast(`Đã lưu phụ cấp: ${money(amount)}`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu phụ cấp", "err"); }
  };

  if (!loaded) return null;
  const list = workers.filter((w) => w.name);
  if (!list.length) return null;

  // tra tiền-1-giờ KHÔNG phân biệt hoa/thường — tên trong báo cáo (gõ tay/Telegram)
  // có thể lệch case với tên đăng ký; server vốn khớp NOCASE, client phải giống
  const hourlyLower: Record<string, number> = {};
  for (const [k, v] of Object.entries(hourly)) hourlyLower[k.trim().toLowerCase()] = v;
  let totPiece = 0, totAllow = 0;
  const rows = list.map((w) => {
    // dòng có SỐ GIỜ = SP tính lương theo giờ → tiền = giờ × tiền-1-giờ của thợ
    const gio = w.gio || 0;
    const rate = hourlyLower[w.name.trim().toLowerCase()] || 0;
    const piece = gio > 0 ? Math.round(gio * rate) : Math.round(w.cay * wage);
    const a = allow[w.name] || 0;
    totPiece += piece; totAllow += a;
    return { name: w.name, cay: w.cay, gio, rate, piece, a, note: (w.note || "").trim() };
  });
  // Xếp hạng theo TIỀN SP (không tính phụ cấp) cho popup "bằng người cao nhất/nhì/ba"
  const ranked = [...rows].sort((x, y) => y.piece - x.piece);
  const MEDALS = ["🥇 Bằng cao nhất", "🥈 Bằng cao nhì", "🥉 Bằng cao ba"];
  const onPickAllow = (v: string) => {
    const name = allowPop;
    if (!name) return;
    if (v === "manual") {
      // mở khoá ô để gõ tay; focus sau khi popup đóng xong
      setManual(name);
      requestAnimationFrame(() => { const el = allowInputs.current[name]; el?.focus(); el?.select(); });
      return;
    }
    let amt = 0;
    if (v.startsWith("t")) amt = ranked[Number(v.slice(1))]?.piece || 0;
    else if (v.startsWith("w:")) amt = rows.find((r2) => r2.name === v.slice(2))?.piece || 0;
    applyAllow(name, amt);
  };

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
      <div class="prod-report-scroll pw-scroll">
        <table class="prod-report-table pw-table">
          <thead><tr><th>Thợ</th><th>Tiền SP</th><th>Phụ cấp</th><th>Tổng</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td class="pw-name">
                  <div>{r.name}</div>
                  {r.note ? <div class="pw-worker-note">{r.note}</div> : null}
                </td>
                <td class="pw-piece">{money(r.piece)}
                  {r.gio > 0
                    ? <span class="muted pw-sub"> {soVN(r.gio)}giờ×{soVN(r.rate)}{r.rate <= 0 ? " ⚠ chưa đặt tiền 1 giờ" : ""}</span>
                    : <span class="muted pw-sub"> {soVN(r.cay)}×{soVN(wage)}</span>}
                </td>
                <td class="pw-allow">
                  {/* Mặc định readOnly (mobile không bật bàn phím) → bấm mở popup chọn
                      nhanh; chọn "Tự nhập" mới mở khoá gõ tay, lưu khi rời ô. */}
                  <input class="pw-input" inputMode="numeric" placeholder="0"
                    ref={(el: any) => { allowInputs.current[r.name] = el; }}
                    readOnly={manual !== r.name}
                    value={draft[r.name] !== undefined ? draft[r.name] : (r.a ? String(r.a) : "")}
                    onClick={() => { if (manual !== r.name) setAllowPop(r.name); }}
                    onInput={(e: any) => setDraft((d) => ({ ...d, [r.name]: e.target.value }))}
                    onBlur={() => { if (manual === r.name) { save(r.name); setManual(null); } }}
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

      {/* Popup chọn nhanh PHỤ CẤP: bằng tiền SP cao nhất/nhì/ba của bảng (không tính
          phụ cấp), bằng 1 thợ cụ thể, hoặc Tự nhập. */}
      <SelectPopup
        open={allowPop != null}
        onClose={() => setAllowPop(null)}
        title={`Phụ cấp — ${allowPop || ""}`}
        value={null}
        options={[
          ...ranked.slice(0, 3).map((r2, k) => ({ value: `t${k}`, label: `${MEDALS[k]} — ${r2.name}`, sub: money(r2.piece) })),
          ...rows.filter((r2) => r2.name !== allowPop).map((r2) => ({ value: `w:${r2.name}`, label: `Bằng ${r2.name}`, sub: money(r2.piece) })),
          { value: "manual", label: "✏️ Tự nhập số tiền" },
        ]}
        onChange={onPickAllow}
      />
    </div>
  );
}
